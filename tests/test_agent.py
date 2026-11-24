import json
from datetime import date, time

from llm import FakeLLM
from pawpal_system import Frequency, Priority
from schedule_agent import import_schedule, parse_response, sample_owner

DAY = date(2026, 11, 23)  # a Monday


def item(**overrides):
    base = {"pet": "Biscuit", "title": "Evening walk", "duration_minutes": 30,
            "priority": "high", "frequency": "daily", "weekday": None,
            "fixed_time": "18:00", "confidence": 0.9}
    base.update(overrides)
    return base


def run(responses, tmp_path, owner=None):
    owner = owner or sample_owner()
    llm = FakeLLM([json.dumps(r) if not isinstance(r, str) else r for r in responses])
    result = import_schedule("text", owner, llm, day=DAY, trace_path=tmp_path / "trace.md")
    return result, owner, llm


def test_valid_tasks_added_first_try(tmp_path):
    result, owner, llm = run([[item(), item(pet="mochi", title="Brush", fixed_time=None,
                                         frequency="weekly", weekday=6, priority="low")]], tmp_path)
    assert result.attempts == 1 and not result.rejected
    assert [a.task.title for a in result.added] == ["Evening walk", "Brush"]
    brush = result.added[1].task
    assert brush.pet.name == "Mochi" and brush.frequency is Frequency.WEEKLY
    assert brush.priority is Priority.LOW
    assert result.added[0].task.fixed_time == time(18, 0)
    assert result.added[0].confidence == 0.9
    assert len(llm.prompts) == 1 and "Biscuit" in llm.prompts[0]


def test_code_fences_stripped():
    assert parse_response("```json\n[{\"a\": 1}]\n```") == [{"a": 1}]


def test_retry_fixes_errors_and_sends_them_back(tmp_path):
    result, owner, llm = run([[item(pet="Rex")], [item()]], tmp_path)
    assert result.attempts == 2 and len(result.added) == 1 and not result.rejected
    assert "unknown pet 'Rex'" in llm.prompts[1]
    assert "Original schedule text" in llm.prompts[1]


def test_gives_up_after_two_retries(tmp_path):
    bad = [item(duration_minutes=0)]
    result, owner, llm = run([bad, bad, bad], tmp_path)
    assert result.attempts == 3 and not result.added
    assert "over 0" in result.rejected[0].reasons[0]
    assert len(owner.all_tasks()) == 2  # nothing added


def test_invalid_json_is_failure_not_crash(tmp_path):
    result, owner, _ = run(["not json", "still not", "nope"], tmp_path)
    assert result.attempts == 3 and not result.added
    assert "not valid JSON" in result.rejected[0].reasons[0]


def test_outside_window_and_bad_enums_rejected(tmp_path):
    items = [item(fixed_time="22:00"), item(title="X", priority="urgent"),
             item(title="Y", frequency="monthly"), item(title="Z", frequency="weekly", weekday=9)]
    result, _, _ = run([items] * 3, tmp_path)
    reasons = " ".join(r for x in result.rejected for r in x.reasons)
    assert "outside the day window" in reasons
    assert "priority" in reasons and "frequency" in reasons and "weekday" in reasons


def test_conflicts_with_existing_and_new_tasks(tmp_path):
    items = [item(title="Play", fixed_time="07:45", duration_minutes=10),  # clashes with walk
             item(title="A", fixed_time="12:00"),
             item(title="B", fixed_time="12:15", pet="Mochi")]  # clashes with A
    result, owner, _ = run([items] * 3, tmp_path)
    assert [a.task.title for a in result.added] == ["A"]
    assert len(result.rejected) == 2
    assert all("conflict" in x.reasons[0] for x in result.rejected)


def test_partial_success_keeps_valid_tasks(tmp_path):
    items = [item(), item(title="Bad", pet="Ghost")]
    result, owner, _ = run([items] * 3, tmp_path)
    assert [a.task.title for a in result.added] == ["Evening walk"]
    assert len(result.rejected) == 1 and result.attempts == 3


def test_llm_exception_handled(tmp_path):
    class Boom:
        def ask(self, prompt, system=""):
            raise RuntimeError("quota")
    result = import_schedule("t", sample_owner(), Boom(), day=DAY, trace_path=tmp_path / "t.md")
    assert not result.added and "quota" in result.rejected[0].reasons[0]


def test_trace_written(tmp_path):
    run([[item(pet="Rex")], [item()]], tmp_path)
    trace = (tmp_path / "trace.md").read_text(encoding="utf-8")
    assert "Attempt 1" in trace and "Attempt 2" in trace
    assert "unknown pet" in trace and "Final outcome" in trace


def test_fake_llm_records_and_queues():
    llm = FakeLLM(["a"], default="d")
    assert llm.ask("p1", "s") == "a" and llm.ask("p2") == "d"
    assert llm.prompts == ["p1", "p2"]
