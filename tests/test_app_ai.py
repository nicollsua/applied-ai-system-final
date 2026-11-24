"""The AI import wired into the Streamlit app, driven with a FakeLLM."""

import json
from datetime import date, time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import app
import schedule_agent
from llm import FakeLLM
from pawpal_system import Owner, Pet, Task

APP = str(Path(__file__).resolve().parents[1] / "app.py")
DAY = date(2026, 11, 23)


@pytest.fixture(autouse=True)
def no_trace_file(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule_agent, "TRACE_PATH", tmp_path / "trace.md")


def task_json(**overrides):
    base = {"pet": "Biscuit", "title": "Evening walk", "duration_minutes": 30,
            "priority": "high", "frequency": "daily", "weekday": None,
            "fixed_time": "18:00", "confidence": 0.9}
    base.update(overrides)
    return base


def owner_with_pets():
    owner = Owner("Jordan", day_start=time(7, 0), day_end=time(21, 0))
    owner.add_pet(Pet("Biscuit", "dog"))
    owner.add_pet(Pet("Mochi", "cat"))
    return owner


# --- helpers -----------------------------------------------------------------


def test_ai_available_with_injected_llm(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert not app.ai_available({})
    assert app.ai_available({"llm": FakeLLM()})


def test_run_import_is_preview_only():
    owner = owner_with_pets()
    state = {"llm": FakeLLM([json.dumps([task_json()])])}
    result = app.run_import(state, owner, "walk", DAY)
    assert len(result.added) == 1 and owner.all_tasks() == []
    assert state["pending_import"] is result


def test_confirm_import_adds_only_kept():
    owner = owner_with_pets()
    state = {"llm": FakeLLM([json.dumps([task_json(), task_json(title="Brush", pet="Mochi",
                                                                fixed_time=None)])])}
    app.run_import(state, owner, "text", DAY)
    added, refused = app.confirm_import(state, owner, [False, True], DAY)
    assert [t.title for t in owner.all_tasks()] == ["Brush"]
    assert state["pending_import"] is None and not refused


def test_describe_proposal_flags_low_confidence():
    owner = owner_with_pets()
    state = {"llm": FakeLLM([json.dumps([task_json(confidence=0.3)])])}
    result = app.run_import(state, owner, "text", DAY)
    line = app.describe_proposal(result.added[0])
    assert "low confidence" in line and "30%" in line and "Biscuit" in line


# --- the real app ------------------------------------------------------------


def launch_with_pets(responses):
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["owner"] = owner_with_pets()
    at.session_state["llm"] = FakeLLM(responses)
    return at.run()


def test_import_journey_preview_then_confirm():
    at = launch_with_pets([json.dumps([
        task_json(),
        task_json(title="Nap", pet="Mochi", fixed_time=None, confidence=0.4),
        task_json(title="Ghost walk", pet="Rex"),
    ])] * 3)
    at.text_area("import_text").set_value("Walk Biscuit at 6pm, Mochi naps")
    at.button(key="import_run_button").click().run()

    owner = at.session_state["owner"]
    assert owner.all_tasks() == []  # nothing added before the owner confirms
    boxes = [c for c in at.checkbox if c.key.startswith("import_keep_")]
    assert [b.value for b in boxes] == [True, False]  # low confidence starts unticked
    reasons = " ".join(m.value for m in at.markdown)
    assert "unknown pet 'Rex'" in reasons

    at.button(key="import_confirm").click().run()
    assert [t.title for t in owner.all_tasks()] == ["Evening walk"]
    assert any("Added 1 task" in s.value for s in at.success)
    assert not at.exception


def test_import_guardrail_message_in_app():
    at = launch_with_pets([])
    at.text_area("import_text").set_value("   ")
    at.button(key="import_run_button").click().run()
    assert "empty" in " ".join(m.value for m in at.markdown).lower()
    assert not at.exception
