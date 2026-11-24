# PawPal+ → Applied AI System (final project)

## App today
Pet care planner. Owner (day_start/day_end window) has Pets; each Pet has Tasks (title, duration_minutes, priority, frequency daily/weekly/once, optional fixed_time). `Schedule.generate()` pins fixed-time tasks, fills gaps with flexible ones by priority. `Scheduler.find_conflicts(day)` reports pinned overlaps. Logic: `pawpal_system.py`. UI: Streamlit `app.py` (helpers take plain dicts so tests run without Streamlit). Tests: `test_*.py`, `tests/`.

## Features being added (must change real app behavior)
1. **Agentic schedule import**: owner pastes plain text → Gemini parses to JSON tasks + confidence → validator (known pet, duration > 0, inside day window, `Scheduler.find_conflicts`) → errors sent back to LLM to fix (max 2 retries) → valid tasks via `Pet.add_task` into `Schedule.generate`; rejected tasks shown with reasons.
2. **Music per task (RAG)**: new `Task.music_enabled: bool = False`. Look up task vibe in `data/vibes.md`, retrieve top 5 from `data/songs.csv`, LLM picks 1-2 ONLY from those with a one-line reason; drop any song not in the CSV. Pick shown next to the task in the plan.

## Reliability
`guardrails.py`: reject empty/oversized input, strip prompt-injection phrases, catch API errors with friendly fallback. Logging via `logging` + `logs/agent_trace.md`. pytest tests. `eval.py` runs predefined inputs, prints pass/fail table + average confidence.

## Planned files
`llm.py` (Gemini wrapper + FakeLLM), `schedule_agent.py`, `music_rag.py`, `guardrails.py`, `eval.py`, `demo.py`, `tests/test_agent.py`, `tests/test_music.py`, `.env.example`. Data exists: `data/songs.csv`, `data/vibes.md`.

## Rules
- Python only. Minimal edits; never rewrite working files. Existing tests must keep passing.
- Tests must pass with FakeLLM and no API key. Key from env `GEMINI_API_KEY`; `.env` in `.gitignore`, never committed.
- Keep `requirements.txt` and `.env.example` current.
- Don't touch `diagrams/uml.mmd` or `reflection.md` (Module 2). Claude may update README, model_card.md, ai_interactions.md and diagrams/architecture.mmd (user approved 2026-11-23); keep numbers in them matching real test/eval output.
- Run pytest before finishing each task; one git commit per finished task with a clear message.
- Replies: code only, no explanations, show only changed lines.
