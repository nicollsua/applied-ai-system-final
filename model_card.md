# Model Card: PawPal+ AI Schedule Import and Music RAG

## System overview

| | |
|---|---|
| **Base project** | PawPal+ (Module 2), a Streamlit pet care planner |
| **Model** | Google Gemini `gemini-3.8-flash` through the `google-genai` SDK ([`llm.py`](llm.py)) |
| **AI features** | 1. Agentic schedule import: plain text becomes validated tasks, with a retry loop ([`schedule_agent.py`](schedule_agent.py))<br>2. Music per task with retrieval-augmented generation ([`music_rag.py`](music_rag.py)) |
| **Reliability layer** | [`guardrails.py`](guardrails.py), human review before tasks are added, [`logs/agent_trace.md`](logs/agent_trace.md), 501 pytest tests, [`eval.py`](eval.py) |
| **Intended use** | One pet owner turning their own routine ("walk Biscuit at 9am…") into a daily plan, plus optional background music for each task |
| **Not intended for** | Veterinary or medical advice, scheduling for many people, or any decision where a wrong time causes harm without a person checking it first |

The model never writes directly into the plan. Everything it produces goes through deterministic checks: known pet, duration over 0, valid values, inside the owner's day, and no clash according to the original `Scheduler.find_conflicts`. The owner then confirms the tasks before they are added. For music, the model can only choose among 5 songs that the retrieval step already pulled from `data/songs.csv`. Anything else it names is dropped.

---

## Limitations and biases

- **Confidence scores are self-reported, not calibrated.** In the live evaluation every added task scored 0.95–0.98. That included the deliberately vague input "Mochi needs some playtime sometime today, maybe 15 minutes", which Gemini rated 0.95. So the number is a hint, not a measurement. The validator and the human review step are the real safety net. The under-0.6 "please check" flag rarely triggers with Gemini.
- **English and keyword based.** Vibe lookup matches English words and a short synonym list ("pill" counts as medication, "brush" as grooming). "Change bedding" matches no vibe and gets a neutral, medium-energy pick. A task described in another language or in slang would get a generic pick.
- **Small, culturally narrow music catalog.** `songs.csv` has 20 songs, almost all English-language Western pop, rock, soul and classical. Retrieval can only be as diverse as that file, so the picks reflect the taste of whoever wrote the CSV.
- **The model resolves ambiguity on its own.** Gemini turned "the dog" into Biscuit and "the cat" into Mochi without asking. That's fine with one dog and one cat, but with two dogs it would have to guess. The owner sees the pet name in the preview, but nothing forces the AI to flag the guess.
- **Single-day, single-owner model.** Conflicts are checked across all pets because one person does every task, and "once" tasks get today's date. Imports like "next Tuesday only" or "every other day" don't fit the daily, weekly or once model and come out approximate.
- **Free-tier limits.** The Gemini free tier allows 20 requests per day for this model. One `eval.py --live` run uses most of that. When the quota runs out, music falls back to retrieval only and imports fail with a friendly message.

## Misuse and how it is prevented

| Risk | Mitigation in the code |
|---|---|
| **Prompt injection** in pasted text ("ignore previous instructions…") | `guardrails.check_input` strips known injection phrases before the model sees the text and tells the owner what it removed. The model's output is still only JSON that has to pass the validator, so even a successful injection can only propose tasks, and those still have to be for a real pet, inside the day, with no clash. |
| **Flooding / cost abuse** with huge inputs | Input over 2,000 characters is refused before any API call. Empty input is refused too. |
| **Made-up songs** or ones not in the catalog | `pick_music` keeps only songs whose id or title is one of the 5 retrieved candidates. Others are logged as dropped (the eval case where the scripted reply names "Thunderstruck" shows this). |
| **Silent wrong schedule** for something important like medication | Nothing is added without the owner confirming. Low-confidence items start unticked. On retry the model is told never to change a time, pet or duration the owner stated just to pass a check, so a clash is shown to the owner rather than quietly moved. |
| **API key leaks** | The key is only read from `.env` (ignored by git). `.env.example` holds a placeholder. Tests use `FakeLLM` and need no key. |
| **Privacy** | Pasted text goes to Google's API. The app is meant for pet routines, and the README tells users not to paste personal information. |

## What surprised me while testing reliability

1. **The model name I relied on had been retired.** The first live run failed with `404 NOT_FOUND: models/gemini-2.5-flash is no longer available`. The app didn't crash: it reported "0 added, 1 rejected" with the reason. That's when I realized error handling was a requirement, not just extra polish. The fix was to switch to `gemini-3.8-flash`.
2. **503 "high demand" errors are common.** Several live runs hit temporary 503s, one of them in the middle of a retry. That led me to add `safe_ask`, which waits 2s and then 5s and tries again. The next live music test failed twice with 503, then succeeded on the third try without me doing anything.
3. **Gemini was smarter than the expected failure.** I expected "Walk the dog at 8am" to be rejected as an unknown pet. Instead Gemini mapped "dog" to Biscuit, and the *validator* caught a different, real problem: the walk overlapped Mochi's 08:00 breakfast. The deterministic check found something the model didn't.
4. **A retry can quietly make things worse.** My first retry prompt said "drop a task only if it cannot be fixed". That gives the model two bad options: move the owner's 7:30 appointment to make the clash disappear, or drop it so the rejection never reaches the owner. I changed the prompt to forbid changing stated details, and I made an empty result count as a rejection ("no pet care tasks found") so it can't vanish.
5. **Confidence didn't separate good from bad inputs** (see Limitations). It averaged 0.95 live and 0.86 with the scripted offline replies.

Final numbers: **501/501 pytest tests pass** with no API key. **`eval.py` offline: 14/14 cases pass.** **`eval.py --live`: 13/13 pass** (one offline-only case is skipped live), with 0.95 average confidence. In that live run, 3 of the 4 music cases used the retrieval-only fallback because the daily quota ran out partway through, and the fallback picks were still grounded in the catalog.

---

## Collaboration with AI during this project

I built the AI extension with Claude Code (an AI coding agent working in my repo) and used a second AI chat assistant to read error messages and plan next steps. My `CLAUDE.md` file gave the agent the project context and rules: minimal edits, existing tests must keep passing, tests run with a fake LLM and no key, one commit per finished task. I gave it one task at a time, then ran the program myself, read the output and the trace log, and decided what to keep.

### A suggestion I accepted

**The `FakeLLM` design**: an object with the same `ask(prompt, system)` method as the Gemini wrapper. It returns queued canned replies and records every prompt it gets. I accepted it as written because it meant:
- every test (501) runs offline, for free and with the same result every time
- tests can check what was *sent* to the model, for example "the retry prompt contains the validation errors" or "the injection phrase was stripped before the prompt"
- `demo.py` and `eval.py` can show the whole pipeline without spending my 20 daily requests

### A suggestion I rejected or changed

**Ignoring the whole `logs/` folder in git.** When the agent built the trace logger it also added `logs/` to `.gitignore`, treating the trace as throwaway runtime output. I reverted that in my own commit ("keep agent_trace.md committed, ignore only .log files"). The trace of real Gemini runs is evidence for this project: it shows the raw model responses, the validation errors, and the retries. A grader can't see it if it isn't in the repo. The agent's choice would be normal for a production app, but it was a poor fit for a portfolio project.

**Also changed:**
- The model name `gemini-2.5-flash` came from the agent's memory and was already retired. I replaced it with the name from the API's own error message.
- The chat assistant suggested fixing that with a PowerShell `(Get-Content …) -replace … | Set-Content llm.py` one-liner. We made the one-line edit directly instead, because in Windows PowerShell 5.1 `Set-Content` can silently re-encode the file.
