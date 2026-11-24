"""Agentic schedule import: plain text -> LLM JSON -> validate -> retry -> add.

Usage:
    python schedule_agent.py "Walk Biscuit every day at 9am for 30 minutes"
    python schedule_agent.py --live "..."   # use Gemini instead of FakeLLM
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol

from guardrails import GuardrailError, LLMUnavailable, check_input, safe_ask
from pawpal_system import (
    Frequency,
    Owner,
    Pet,
    Priority,
    Scheduler,
    Task,
    to_minutes,
)

logger = logging.getLogger("schedule_agent")

MAX_RETRIES = 2
LOW_CONFIDENCE = 0.6  # below this the UI asks the owner to double-check
TRACE_PATH = Path(__file__).resolve().parent / "logs" / "agent_trace.md"

SYSTEM_PROMPT = (
    "You convert a pet owner's plain-text schedule into pet care tasks. "
    "Return ONLY a JSON array, no prose and no code fences. Each element is an "
    "object with exactly these keys: "
    '"pet" (string, one of the known pet names), '
    '"title" (string), '
    '"duration_minutes" (integer > 0), '
    '"priority" ("high" | "medium" | "low"), '
    '"frequency" ("daily" | "weekly" | "once"), '
    '"weekday" (integer 0-6 where 0 is Monday, required for weekly, else null), '
    '"fixed_time" ("HH:MM" 24-hour or null if flexible), '
    '"confidence" (number 0-1, how sure you are of this task).'
)


class LLM(Protocol):
    def ask(self, prompt: str, system: str = "") -> str: ...


@dataclass
class AddedTask:
    task: Task
    confidence: float
    pet: Pet | None = None

    @property
    def low_confidence(self) -> bool:
        return self.confidence < LOW_CONFIDENCE


@dataclass
class RejectedItem:
    item: Any
    reasons: list[str]


@dataclass
class ImportResult:
    added: list[AddedTask] = field(default_factory=list)
    rejected: list[RejectedItem] = field(default_factory=list)
    attempts: int = 0
    warnings: list[str] = field(default_factory=list)
    committed: bool = True

    @property
    def ok(self) -> bool:
        return bool(self.added) and not self.rejected

    @property
    def average_confidence(self) -> float:
        if not self.added:
            return 0.0
        return sum(a.confidence for a in self.added) / len(self.added)


# --- Prompts -----------------------------------------------------------------


def _context(owner: Owner) -> str:
    pets = ", ".join(f"{p.name} ({p.species})" for p in owner.pets) or "none"
    return (
        f"Known pets: {pets}\n"
        f"Owner's day window: {owner.day_start:%H:%M}-{owner.day_end:%H:%M}\n"
    )


def build_prompt(text: str, owner: Owner) -> str:
    return f"{_context(owner)}\nSchedule text:\n{text}\n\nReturn the JSON array."


def build_retry_prompt(text: str, owner: Owner, previous: str, errors: list[str]) -> str:
    error_lines = "\n".join(f"- {e}" for e in errors)
    return (
        f"{_context(owner)}\nOriginal schedule text:\n{text}\n\n"
        f"Your previous answer:\n{previous}\n\n"
        f"It had these problems:\n{error_lines}\n\n"
        "Return a corrected, complete JSON array (ONLY JSON). Fix formatting "
        "and misread details using the original text. Never change a time, "
        "pet, or duration the owner actually stated just to make a check "
        "pass; if a problem can only be fixed that way, return that task "
        "unchanged so the owner sees why it was refused."
    )


# --- Parsing -----------------------------------------------------------------

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_response(raw: str) -> list[Any]:
    """Return the JSON list from an LLM reply. Raises ValueError if invalid."""
    cleaned = _FENCE.sub("", (raw or "").strip()).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"response was not valid JSON ({exc.msg})") from exc
    if isinstance(data, dict) and isinstance(data.get("tasks"), list):
        data = data["tasks"]
    if not isinstance(data, list):
        raise ValueError("response JSON must be a list of tasks")
    return data


# --- Validation --------------------------------------------------------------


def _label(index: int, item: Any) -> str:
    title = item.get("title") if isinstance(item, dict) else None
    return f"item {index + 1} ({title!r})" if title else f"item {index + 1}"


def item_to_task(item: Any, owner: Owner, day: date) -> tuple[Task | None, Pet | None, float, list[str]]:
    """Convert one JSON item to an unattached Task. Returns (task, pet, confidence, errors)."""
    if not isinstance(item, dict):
        return None, None, 0.0, ["item is not a JSON object"]

    errors: list[str] = []

    pet_name = str(item.get("pet") or "").strip()
    pet = next((p for p in owner.pets if p.name.lower() == pet_name.lower()), None)
    if pet is None:
        known = ", ".join(p.name for p in owner.pets)
        errors.append(f"unknown pet {pet_name!r} (known pets: {known})")

    title = str(item.get("title") or "").strip()
    if not title:
        errors.append("title is missing")

    duration = item.get("duration_minutes")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration != int(duration):
        errors.append(f"duration_minutes must be a whole number, got {duration!r}")
        duration = None
    elif duration <= 0:
        errors.append(f"duration_minutes must be over 0, got {duration}")
    else:
        duration = int(duration)

    try:
        priority = Priority(str(item.get("priority", "")).lower())
    except ValueError:
        errors.append(f"priority must be high/medium/low, got {item.get('priority')!r}")
        priority = None

    try:
        frequency = Frequency(str(item.get("frequency", "")).lower())
    except ValueError:
        errors.append(f"frequency must be daily/weekly/once, got {item.get('frequency')!r}")
        frequency = None

    weekday = item.get("weekday")
    if frequency is Frequency.WEEKLY:
        if isinstance(weekday, bool) or not isinstance(weekday, int) or not 0 <= weekday <= 6:
            errors.append(f"weekly task needs weekday 0-6, got {weekday!r}")
    else:
        weekday = None

    fixed_time = None
    raw_time = item.get("fixed_time")
    if raw_time not in (None, ""):
        try:
            fixed_time = datetime.strptime(str(raw_time), "%H:%M").time()
        except ValueError:
            errors.append(f"fixed_time must be 'HH:MM' or null, got {raw_time!r}")

    if fixed_time is not None and isinstance(duration, int) and duration > 0:
        start = to_minutes(fixed_time)
        if start < to_minutes(owner.day_start) or start + duration > to_minutes(owner.day_end):
            errors.append(
                f"fixed_time {fixed_time:%H:%M} for {duration} min is outside the "
                f"day window {owner.day_start:%H:%M}-{owner.day_end:%H:%M}"
            )

    confidence = item.get("confidence", 0.0)
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append(f"confidence must be a number 0-1, got {confidence!r}")
        confidence = 0.0

    if errors:
        return None, pet, float(confidence), errors

    task = Task(
        title=title,
        duration_minutes=duration,
        priority=priority,
        frequency=frequency,
        weekday=weekday,
        due_date=day if frequency is Frequency.ONCE else None,
        fixed_time=fixed_time,
    )
    return task, pet, float(confidence), []


def new_conflicts(owner: Owner, accepted: list[tuple[Task, Pet]], task: Task, pet: Pet, day: date) -> list[str]:
    """Return conflicts that adding `task` would create, via Scheduler.find_conflicts.

    Builds a throwaway owner holding every existing task plus the already
    accepted new ones, and compares find_conflicts with and without the
    candidate over a full week so daily/weekly/once tasks all meet.
    """
    if not task.is_pinned():
        return []

    base = [t for p in owner.pets for t in p.tasks]
    base += [replace(t, pet=p) for t, p in accepted]
    candidate = replace(task, pet=pet)

    def shadow(tasks: list[Task]) -> Scheduler:
        holder = Pet(name="_shadow", species="")
        holder.tasks = tasks  # direct assign: keeps each task's real pet link
        return Scheduler(Owner(owner.name, owner.day_start, owner.day_end, [holder]))

    before, after = shadow(base), shadow(base + [candidate])
    found: list[str] = []
    for offset in range(7):
        d = day + timedelta(days=offset)
        old = set(before.find_conflicts(d))
        for warning in after.find_conflicts(d):
            if warning not in old and warning not in found:
                found.append(warning)
    return found


def validate(items: list[Any], owner: Owner, day: date) -> tuple[list[tuple[Task, Pet, float]], list[RejectedItem]]:
    valid: list[tuple[Task, Pet, float]] = []
    rejected: list[RejectedItem] = []
    for index, item in enumerate(items):
        task, pet, confidence, errors = item_to_task(item, owner, day)
        if not errors:
            errors = new_conflicts(owner, [(t, p) for t, p, _ in valid], task, pet, day)
            errors = [f"conflict: {e}" for e in errors]
        if errors:
            rejected.append(RejectedItem(item, [f"{_label(index, item)}: {e}" for e in errors]))
        else:
            valid.append((task, pet, confidence))
    return valid, rejected


# --- Trace -------------------------------------------------------------------


class Trace:
    def __init__(self, path: Path | str | None):
        self.path = Path(path) if path else None

    def write(self, heading: str, body: str = "") -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(f"### {heading}\n\n")
            if body:
                f.write(f"{body}\n\n")


def _block(text: str) -> str:
    return f"```\n{text}\n```"


# --- Agent -------------------------------------------------------------------


def import_schedule(
    text: str,
    owner: Owner,
    llm: LLM,
    day: date | None = None,
    max_retries: int = MAX_RETRIES,
    trace_path: Path | str | None = "default",
    commit: bool = True,
) -> ImportResult:
    """Parse plain text into tasks with the LLM, validate, retry, and add the valid ones.

    With commit=False nothing is added: result.added holds the validated
    tasks (each with its pet) so a person can review them first and then
    call commit_tasks() with the ones they keep.
    """
    day = day or date.today()
    trace = Trace(TRACE_PATH if trace_path == "default" else trace_path)
    result = ImportResult(committed=commit)

    trace.write(
        f"Import run {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Owner: {owner.name}; pets: {', '.join(p.name for p in owner.pets)}\n\n"
        f"Input:\n{_block(text or '')}",
    )

    try:
        checked = check_input(text)
    except GuardrailError as exc:
        logger.warning("Input rejected by guardrail: %s", exc)
        result.rejected.append(RejectedItem(text, [f"guardrail: {exc}"]))
        trace.write("Final outcome", f"Input rejected by guardrail: {exc}")
        return result
    text = checked.text
    result.warnings.extend(checked.warnings)
    for warning in checked.warnings:
        trace.write("Guardrail", warning)
    logger.info("Import started for %s (%d chars)", owner.name, len(text))

    prompt = build_prompt(text, owner)
    items: list[Any] | None = None
    errors: list[str] = []
    valid: list[tuple[Task, Pet, float]] = []
    rejected: list[RejectedItem] = []

    for attempt in range(max_retries + 1):
        result.attempts = attempt + 1
        summary = "initial parse" if attempt == 0 else f"retry {attempt} with {len(errors)} error(s)"
        logger.info("Attempt %d: %s", result.attempts, summary)

        try:
            raw = safe_ask(llm, prompt, SYSTEM_PROMPT)
        except LLMUnavailable as exc:  # API/network failures must not crash the app
            trace.write(
                f"Attempt {result.attempts} ({summary})",
                f"LLM call failed: {exc}\n\nDetails: {exc.__cause__}",
            )
            errors = [f"AI unavailable: {exc}"]
            break

        logger.debug("Raw response: %s", raw)
        try:
            items = parse_response(raw)
            valid, rejected = validate(items, owner, day)
            errors = [r for item in rejected for r in item.reasons]
        except ValueError as exc:
            errors = [str(exc)]
            valid, rejected = [], []

        trace.write(
            f"Attempt {result.attempts} ({summary})",
            f"Prompt summary: {summary}, {len(prompt)} chars\n\n"
            f"Raw response:\n{_block(raw)}\n\n"
            "Validation errors:\n" + ("\n".join(f"- {e}" for e in errors) or "- none"),
        )
        logger.info("Attempt %d: %d valid, %d error(s)", result.attempts, len(valid), len(errors))

        if not errors:
            break
        if attempt < max_retries:
            prompt = build_retry_prompt(text, owner, raw, errors)

    if items is None or (errors and not valid and not rejected):
        # Never got a usable list (invalid JSON or API failure on the last try).
        result.rejected.append(RejectedItem(text, errors or ["no tasks returned"]))
    else:
        result.rejected.extend(rejected)
        if not items:
            result.rejected.append(RejectedItem(text, ["no pet care tasks found in the text"]))

    for task, pet, confidence in valid:
        if commit:
            pet.add_task(task)
        result.added.append(AddedTask(task, confidence, pet))

    verb = "added" if commit else "proposed for review"
    outcome = (
        f"{len(result.added)} {verb}, {len(result.rejected)} rejected, "
        f"{result.attempts} attempt(s)"
    )
    logger.info("Import finished: %s", outcome)
    lines = [f"- {verb}: {a.task.title} ({a.pet.name}, confidence {a.confidence:.2f})" for a in result.added]
    lines += [f"- rejected: {'; '.join(r.reasons)}" for r in result.rejected]
    trace.write("Final outcome", outcome + ("\n\n" + "\n".join(lines) if lines else ""))
    return result


def commit_tasks(owner: Owner, proposed: list[AddedTask], day: date | None = None) -> tuple[list[AddedTask], list[RejectedItem]]:
    """Add the tasks a person approved, re-checking conflicts at commit time.

    The owner may have edited their tasks between preview and confirm, so a
    task that now clashes is refused rather than added blindly.
    """
    day = day or date.today()
    added: list[AddedTask] = []
    refused: list[RejectedItem] = []
    for proposal in proposed:
        clashes = new_conflicts(owner, [], proposal.task, proposal.pet, day)
        if clashes:
            refused.append(RejectedItem(proposal.task.title, [f"conflict: {c}" for c in clashes]))
            continue
        proposal.pet.add_task(proposal.task)
        added.append(proposal)
    logger.info("Committed %d task(s), refused %d", len(added), len(refused))
    return added, refused


# --- CLI ---------------------------------------------------------------------


def sample_owner() -> Owner:
    owner = Owner("Jordan", day_start=time(7, 0), day_end=time(21, 0))
    biscuit = Pet("Biscuit", "dog")
    mochi = Pet("Mochi", "cat")
    owner.add_pet(biscuit)
    owner.add_pet(mochi)
    biscuit.add_task(Task("Morning walk", 30, Priority.HIGH, fixed_time=time(7, 30)))
    mochi.add_task(Task("Breakfast", 10, Priority.HIGH, fixed_time=time(8, 0)))
    return owner


SAMPLE_RESPONSE = json.dumps([
    {"pet": "Biscuit", "title": "Evening walk", "duration_minutes": 30, "priority": "high",
     "frequency": "daily", "weekday": None, "fixed_time": "18:00", "confidence": 0.9},
    {"pet": "Mochi", "title": "Brush coat", "duration_minutes": 15, "priority": "medium",
     "frequency": "weekly", "weekday": 6, "fixed_time": None, "confidence": 0.8},
])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a plain-text pet schedule.")
    parser.add_argument("text", help="schedule text to import")
    parser.add_argument("--live", action="store_true", help="use Gemini instead of FakeLLM")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    from llm import FakeLLM, GeminiLLM

    llm = GeminiLLM() if args.live else FakeLLM(default=SAMPLE_RESPONSE)
    owner = sample_owner()
    result = import_schedule(args.text, owner, llm,
                             trace_path="default" if args.live else None)

    print(f"\nAttempts: {result.attempts}")
    for warning in result.warnings:
        print(f"Guardrail: {warning}")
    print("Added:")
    for a in result.added or []:
        t = a.task
        when = f"{t.fixed_time:%H:%M}" if t.fixed_time else "flexible"
        print(f"  {t.title} ({t.pet.name}) {t.duration_minutes} min, {t.priority.value}, "
              f"{t.frequency.value}, {when}, confidence {a.confidence:.2f}")
    if not result.added:
        print("  (none)")
    print("Rejected:")
    for r in result.rejected:
        print("  " + "; ".join(r.reasons))
    if not result.rejected:
        print("  (none)")

    print("\n" + Scheduler(owner).plan_for(date.today()).explain())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
