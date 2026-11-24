import json

import pytest

import guardrails
from llm import FakeLLM
from music_rag import find_vibe, load_songs, load_vibes, pick_music, retrieve
from pawpal_system import Task


def test_vibes_and_songs_load():
    vibes = load_vibes()
    assert len(vibes) == 9
    walk = next(v for v in vibes if v.name == "walk")
    assert (walk.energy_min, walk.energy_max) == (5, 8) and "outdoors" in walk.words
    assert len(load_songs()) == 20


@pytest.mark.parametrize("title,vibe", [
    ("Morning walk", "walk"),
    ("Evening walks", "walk"),
    ("Fetch in the yard", "play / fetch"),
    ("Brush Mochi", "grooming"),
    ("Give insulin", "medication / vet visit"),
    ("Vet visit", "medication / vet visit"),
    ("Breakfast", "feeding"),
    ("Scoop litter box", "cleaning"),
    ("Change bedding", None),
    ("Bedtime cuddle", "bedtime / cuddle"),
])
def test_find_vibe(title, vibe):
    found = find_vibe(title)
    assert (found.name if found else None) == vibe


def test_retrieve_respects_vibe():
    calm = retrieve(find_vibe("Bath time"))
    assert len(calm) == 5 and all(s.energy <= 5 for s in calm)
    loud = retrieve(find_vibe("Play fetch"))
    assert all(s.energy >= 7 for s in loud[:3])


def test_llm_picks_only_from_candidates():
    task = Task("Bath", 20)
    candidates = retrieve(find_vibe("Bath"))
    first = candidates[0]
    llm = FakeLLM([json.dumps([
        {"id": first.id, "reason": "soothing"},
        {"id": 999, "title": "Thunderstruck", "reason": "invented"},
        {"id": 4, "reason": "Queen is not calm"},  # in CSV but not retrieved
    ])])
    pick = pick_music(task, llm)
    assert [s.id for s, _ in pick.picks] == [first.id]
    assert pick.picks[0][1] == "soothing" and not pick.used_fallback
    assert len(pick.dropped) == 2
    assert "Candidates:" in llm.prompts[0] and "bath" in llm.prompts[0].lower()


def test_max_two_picks_and_title_accepted():
    candidates = retrieve(find_vibe("Morning walk"))
    llm = FakeLLM([json.dumps([{"title": c.title, "reason": "r"} for c in candidates])])
    pick = pick_music(Task("Morning walk", 30), llm)
    assert len(pick.picks) == 2


def test_fallback_without_llm():
    pick = pick_music(Task("Give pill", 5))
    assert pick.used_fallback and len(pick.picks) == 1
    assert pick.picks[0][0] in pick.candidates
    assert "medication" in pick.picks[0][1]


def test_fallback_on_bad_json_or_api_error(monkeypatch):
    monkeypatch.setattr(guardrails, "_sleep", lambda s: None)
    assert pick_music(Task("Walk", 30), FakeLLM(["no json here"])).used_fallback

    class Down:
        def ask(self, prompt, system=""):
            raise RuntimeError("503 UNAVAILABLE")
    assert pick_music(Task("Walk", 30), Down()).used_fallback


def test_unknown_task_still_gets_a_pick():
    pick = pick_music(Task("Dentist paperwork", 10))
    assert pick.vibe is None and pick.picks


def test_task_music_flag_defaults_off():
    assert Task("Walk", 30).music_enabled is False
