"""Music per task, with retrieval-augmented generation.

Pipeline for one task:
  1. Retrieve the task's vibe from data/vibes.md (energy range + mood words),
     matching the task title against vibe names and a few synonyms.
  2. Retrieve the 5 songs from data/songs.csv that best fit that vibe
     (tag match, energy inside the range, mood words).
  3. Generate: the LLM sees ONLY those 5 songs plus the vibe text and picks
     1-2 with a one-line reason.
  4. Guard: any pick that is not one of the 5 retrieved songs is dropped.
     If the LLM fails or picks nothing valid, the top retrieved song is used.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from guardrails import LLMUnavailable, safe_ask
from pawpal_system import Task

logger = logging.getLogger("music_rag")

DATA_DIR = Path(__file__).resolve().parent / "data"
VIBES_PATH = DATA_DIR / "vibes.md"
SONGS_PATH = DATA_DIR / "songs.csv"
TOP_K = 5

# Words in a task title that point to a vibe even though the vibe name is absent.
ALIASES = {
    "walk": ["walk", "stroll", "hike", "jog", "run", "potty"],
    "play / fetch": ["play", "fetch", "ball", "toy", "zoomies"],
    "training": ["train", "training", "trick", "obedience", "practice"],
    "bath": ["bath", "wash", "shower", "rinse"],
    "grooming": ["groom", "grooming", "brush", "comb", "nail", "trim", "teeth"],
    "feeding": ["feed", "feeding", "food", "meal", "breakfast", "lunch", "dinner", "treat", "water"],
    "medication / vet visit": ["medication", "meds", "pill", "insulin", "drops", "vet", "vaccine", "medicine", "injection"],
    "bedtime / cuddle": ["bed", "bedtime", "sleep", "nap", "cuddle", "rest", "wind down"],
    "cleaning": ["clean", "cleaning", "litter", "cage", "tank", "poop", "scoop", "vacuum"],
}

SYSTEM_PROMPT = (
    "You pick background music for a pet care task. You may ONLY choose songs "
    "from the numbered candidate list you are given; never suggest any other "
    "song. Return ONLY a JSON array of 1 or 2 objects: "
    '{"id": <candidate id>, "reason": "<one short sentence>"}.'
)


@dataclass(frozen=True)
class Vibe:
    name: str
    energy_min: int
    energy_max: int
    words: frozenset[str]
    text: str

    @property
    def keywords(self) -> list[str]:
        return [k.strip().split()[0] for k in self.name.split("/")]


@dataclass(frozen=True)
class Song:
    id: int
    title: str
    artist: str
    genre: str
    energy: int
    mood: str
    tags: tuple[str, ...]

    def describe(self) -> str:
        return f"{self.title} by {self.artist}"


@dataclass
class MusicPick:
    task_title: str
    vibe: Vibe | None
    candidates: list[Song]
    picks: list[tuple[Song, str]] = field(default_factory=list)
    used_fallback: bool = False
    dropped: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.picks:
            return ""
        return "; ".join(f"{song.describe()} ({reason})" for song, reason in self.picks)


# --- Loading ----------------------------------------------------------------


_VIBE_LINE = re.compile(r"^-\s*(?P<name>[^:]+):\s*(?P<body>.+)$")
_ENERGY = re.compile(r"energy\s+(\d+)\s*-\s*(\d+)", re.IGNORECASE)


@lru_cache(maxsize=4)
def load_vibes(path: Path = VIBES_PATH) -> tuple[Vibe, ...]:
    vibes = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        match = _VIBE_LINE.match(line.strip())
        if not match:
            continue
        body = match.group("body")
        energy = _ENERGY.search(body)
        low, high = (int(energy.group(1)), int(energy.group(2))) if energy else (1, 10)
        words = frozenset(w for w in re.findall(r"[a-z]+", _ENERGY.sub("", body).lower()) if len(w) > 2)
        vibes.append(Vibe(match.group("name").strip(), low, high, words, body.strip()))
    return tuple(vibes)


@lru_cache(maxsize=4)
def load_songs(path: Path = SONGS_PATH) -> tuple[Song, ...]:
    with Path(path).open(encoding="utf-8", newline="") as f:
        return tuple(
            Song(int(r["id"]), r["title"], r["artist"], r["genre"], int(r["energy"]),
                 r["mood"].strip().lower(), tuple(t.strip().lower() for t in r["tags"].split("|")))
            for r in csv.DictReader(f)
        )


# --- Retrieval --------------------------------------------------------------


def find_vibe(title: str, vibes: tuple[Vibe, ...] | None = None) -> Vibe | None:
    """Return the vibe whose name or synonyms appear in the task title."""
    vibes = load_vibes() if vibes is None else vibes
    lowered = title.lower()
    for vibe in vibes:
        terms = ALIASES.get(vibe.name, []) + vibe.keywords
        if any(re.search(rf"\b{re.escape(t)}(s|es|ing|ed)?\b", lowered) for t in terms):
            return vibe
    return None


def score(song: Song, vibe: Vibe) -> float:
    s = 0.0
    if any(k in song.tags for k in vibe.keywords):
        s += 3
    if vibe.energy_min <= song.energy <= vibe.energy_max:
        s += 2
    else:
        s -= 0.5 * min(abs(song.energy - vibe.energy_min), abs(song.energy - vibe.energy_max))
    if song.mood in vibe.words:
        s += 1
    s += 0.5 * sum(1 for t in song.tags if t in vibe.words)
    return s


def retrieve(vibe: Vibe | None, songs: tuple[Song, ...] | None = None, k: int = TOP_K) -> list[Song]:
    """Return the k songs that best fit the vibe (calm middle-energy if none)."""
    songs = load_songs() if songs is None else songs
    if vibe is None:
        return sorted(songs, key=lambda s: (abs(s.energy - 5), s.id))[:k]
    return sorted(songs, key=lambda s: (-score(s, vibe), s.id))[:k]


# --- Generation -------------------------------------------------------------


def build_prompt(task: Task, vibe: Vibe | None, candidates: list[Song]) -> str:
    vibe_text = f"{vibe.name}: {vibe.text}" if vibe else "no specific vibe, keep it pleasant"
    lines = [
        f"{s.id}. {s.title} by {s.artist} (genre {s.genre}, energy {s.energy}/10, "
        f"mood {s.mood}, tags {', '.join(s.tags)})"
        for s in candidates
    ]
    return (
        f"Task: {task.title} ({task.duration_minutes} min)\n"
        f"Vibe guide: {vibe_text}\n\nCandidates:\n" + "\n".join(lines) +
        "\n\nPick 1 or 2 candidate ids that best fit. Return the JSON array."
    )


def _parse(raw: str) -> list[dict]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip()).strip()
    data = json.loads(cleaned)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("not a list")
    return [d for d in data if isinstance(d, dict)]


def pick_music(task: Task, llm=None, k: int = TOP_K) -> MusicPick:
    """Retrieve candidates for a task and let the LLM choose among them only."""
    vibe = find_vibe(task.title)
    candidates = retrieve(vibe, k=k)
    result = MusicPick(task.title, vibe, candidates)
    by_id = {s.id: s for s in candidates}
    catalog_titles = {s.title.lower() for s in load_songs()}
    logger.info("Music for %r: vibe=%s, candidates=%s", task.title,
                vibe.name if vibe else None, [s.id for s in candidates])

    if llm is not None:
        try:
            raw = safe_ask(llm, build_prompt(task, vibe, candidates), SYSTEM_PROMPT)
            for entry in _parse(raw):
                song = by_id.get(entry.get("id")) if isinstance(entry.get("id"), int) else None
                if song is None:  # also accept a title, but only if it's a candidate
                    title = str(entry.get("title", "")).lower()
                    song = next((s for s in candidates if s.title.lower() == title), None)
                if song is None:
                    label = entry.get("title") or entry.get("id")
                    where = "in songs.csv" if str(label).lower() in catalog_titles else "not in songs.csv"
                    result.dropped.append(f"{label} (not a retrieved candidate, {where})")
                    continue
                if song not in [p[0] for p in result.picks] and len(result.picks) < 2:
                    reason = str(entry.get("reason") or "fits the task's vibe").strip()
                    result.picks.append((song, reason[:160]))
        except (LLMUnavailable, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Music pick fell back to retrieval: %s", exc)

    if result.dropped:
        logger.warning("Dropped songs outside the candidates: %s", result.dropped)
    if not result.picks and candidates:
        result.used_fallback = True
        why = f"top match for a {vibe.name} vibe" if vibe else "closest calm-to-medium energy match"
        result.picks.append((candidates[0], why))
    return result
