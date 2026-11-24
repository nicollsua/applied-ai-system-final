# AI Interactions Log

This file covers two things:
1. the **agentic workflow traces** for the final project's *Agentic Workflow Enhancement* stretch: the import agent's intermediate steps, each attempt and retry
2. how I used an **AI coding agent** to build the project

---

## Agentic workflow traces (stretch feature)

The import agent ([`schedule_agent.py`](schedule_agent.py)) is a multi-step decision chain:

```text
guardrail check -> LLM parse (JSON + confidence) -> validate each task with deterministic tools
   (pet lookup, enum checks, day window, Scheduler.find_conflicts on a shadow owner)
-> decision: all valid?  yes -> preview for human review -> commit_tasks (re-check, Pet.add_task)
                         no  -> send error list + original text back to the LLM (max 2 retries)
                                -> still failing -> reject with reasons, keep the valid subset
```

Every live run appends its intermediate steps to a committed log: **[`logs/agent_trace.md`](logs/agent_trace.md)**. Each entry has the input, any guardrail action, then for each attempt the prompt summary, the raw model response and the validation errors, and finally the outcome. The two excerpts below are real Gemini runs, copied from that file.

### Trace 1: the validator finds a clash, the agent retries, the API fails mid-retry

```text
### Import run 2026-11-23 18:53:17
Owner: Jordan; pets: Biscuit, Mochi
Input:
  Walk the dog at 8am for 30 minutes, then feed the cat at noon

### Attempt 1 (initial parse)
Prompt summary: initial parse, 172 chars
Raw response:
  [{"pet":"Biscuit","title":"Walk Biscuit","duration_minutes":30,"priority":"medium","frequency":"daily",
    "weekday":null,"fixed_time":"08:00","confidence":0.95},
   {"pet":"Mochi","title":"Feed Mochi","duration_minutes":15,"priority":"high","frequency":"daily",
    "weekday":null,"fixed_time":"12:00","confidence":0.95}]
Validation errors:
- item 1 ('Walk Biscuit'): conflict: Mochi and Biscuit overlap: Breakfast runs 08:00-08:10 but Walk Biscuit starts 08:00

### Attempt 2 (retry 1 with 1 error(s))
LLM call failed: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. ...'}}

### Final outcome
1 added, 1 rejected, 2 attempt(s)
- added: Feed Mochi (Mochi, confidence 0.95)
- rejected: item 1 ('Walk Biscuit'): conflict: Mochi and Biscuit overlap: Breakfast runs 08:00-08:10 but Walk Biscuit starts 08:00
```

How the agent reasoned at each step:
- **Step 1 (model):** the model resolved "the dog" and "the cat" to the known pets on its own.
- **Step 2 (tools):** the deterministic conflict tool found a clash the model couldn't know about, because Mochi's 08:00 breakfast was already in the plan.
- **Step 3 (retry):** the agent decided to retry with the error list.
- **Step 4 (failure):** the API failed, so the agent stopped safely and kept the one task that was valid. Since then, `guardrails.safe_ask` retries temporary 503s automatically before giving up.

### Trace 2: a clean single-pass run

```text
### Import run 2026-11-23 18:51:23
Input:
  Walk Biscuit at 9am for 30 minutes, then feed Mochi at noon for 10 minutes
### Attempt 1 (initial parse)
Prompt summary: initial parse, 185 chars
Raw response:
  [{"pet": "Biscuit", "title": "Walk Biscuit", "duration_minutes": 30, "priority": "medium", "frequency": "daily",
    "weekday": null, "fixed_time": "09:00", "confidence": 0.95},
   {"pet": "Mochi", "title": "Feed Mochi", "duration_minutes": 10, "priority": "high", "frequency": "daily",
    "weekday": null, "fixed_time": "12:00", "confidence": 0.95}]
Validation errors:
- none
### Final outcome
2 added, 0 rejected, 1 attempt(s)
```

### Full retry chain (3 attempts, reproducible offline)

`python demo.py`, scenario 2, shows the full loop: the guardrail strips an injection phrase, attempt 1 finds an unknown pet and a clash, the agent retries twice, and the final outcome keeps the one valid task and refuses the other two with reasons. Output: [`logs/demo_output.txt`](logs/demo_output.txt). In the live evaluation ([`logs/eval_results_live.md`](logs/eval_results_live.md)), the *clash* and *outside the day window* cases also used all 3 attempts before refusing.

The music RAG chain logs its steps through the `music_rag` logger: the vibe it retrieved, the 5 candidate ids, any dropped picks, and whether it used the fallback.

---

## Agent Workflow (SF7)

**What task did you give the agent?**

I used Claude Code as a coding agent in my repo, with a `CLAUDE.md` file describing the app, the two planned AI features and the rules: minimal edits, existing tests must keep passing, tests must run with a fake LLM and no API key, one commit per finished task. I gave it one task at a time:
1. Gemini wrapper + `FakeLLM`
2. the schedule import agent with validation, retries and trace logging
3. guardrails
4. adding the import to the Streamlit app with a review step
5. the music RAG
6. `eval.py` and `demo.py`
7. the docs

**What did the agent do?**

For each task it read the relevant code first, for example `pawpal_system.py`, so it could reuse `Scheduler.find_conflicts` and `Pet.add_task` instead of rewriting them. It also read the existing UI tests before touching `app.py`. Then it:
- wrote the new modules and their tests
- ran the full pytest suite
- ran the CLI, demo and eval, live against Gemini where useful
- fixed failures
- made one commit per step

Examples of it reacting to what it found:
- The existing UI tests check the exact subheaders and button order, so it put the new sections in expanders after the task form.
- When live runs hit 503 errors, it proposed the automatic retry.
- When it noticed that offline demo runs were mixing scripted replies into the real trace log, it removed those entries and limited the trace to live runs.

**What did you have to verify or fix manually?**

- **Model name:** the agent chose `gemini-2.5-flash` from memory, and it was already retired. The first live run failed with a 404. The error message named the replacement, `gemini-3.8-flash`.
- **`logs/` in `.gitignore`:** the agent ignored the whole folder. I reverted that so `agent_trace.md` stays committed as evidence (my commit "keep agent_trace.md committed, ignore only .log files").
- **Live behavior:** I ran the live commands myself and read the trace. The chat assistant I used predicted that "the dog" and "the cat" would be rejected as unknown pets. In fact Gemini mapped them correctly and the validator caught a clash instead. That's a reminder that predictions about model behavior have to be checked against real runs.
- **Retry prompt:** reviewing the retry loop, we found the first prompt let the model drop or move tasks it couldn't fix. We changed it so the owner's stated details are never altered and an empty reply counts as a rejection.
