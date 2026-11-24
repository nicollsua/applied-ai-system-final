# Agent trace (real Gemini runs)

Appended by schedule_agent.import_schedule on every live import: input, each attempt (prompt summary, raw model response, validation errors), retries, and the final outcome. Offline FakeLLM runs (tests, demo.py, eval.py without --live) are not recorded here.

### Import run 2026-11-23 18:48:02

Owner: Jordan; pets: Biscuit, Mochi

Input:
```
Walk the dog at 8am for 30 minutes, then feed the cat at noon
```

### Attempt 1 (initial parse)

LLM call failed: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'This model models/gemini-2.5-flash is no longer available to new users. Please update your code to use models/gemini-3.8-flash for the latest features and improvements. We recommend you to use the Interactions API (https://aistudio.google.com/docs/get-started).', 'status': 'NOT_FOUND'}}

### Final outcome

0 added, 1 rejected, 1 attempt(s)

- rejected: LLM call failed: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'This model models/gemini-2.5-flash is no longer available to new users. Please update your code to use models/gemini-3.8-flash for the latest features and improvements. We recommend you to use the Interactions API (https://aistudio.google.com/docs/get-started).', 'status': 'NOT_FOUND'}}

### Import run 2026-11-23 18:51:23

Owner: Jordan; pets: Biscuit, Mochi

Input:
```
Walk Biscuit at 9am for 30 minutes, then feed Mochi at noon for 10 minutes
```

### Attempt 1 (initial parse)

Prompt summary: initial parse, 185 chars

Raw response:
```
[{"pet": "Biscuit", "title": "Walk Biscuit", "duration_minutes": 30, "priority": "medium", "frequency": "daily", "weekday": null, "fixed_time": "09:00", "confidence": 0.95}, {"pet": "Mochi", "title": "Feed Mochi", "duration_minutes": 10, "priority": "high", "frequency": "daily", "weekday": null, "fixed_time": "12:00", "confidence": 0.95}]
```

Validation errors:
- none

### Final outcome

2 added, 0 rejected, 1 attempt(s)

- added: Walk Biscuit (Biscuit, confidence 0.95)
- added: Feed Mochi (Mochi, confidence 0.95)

### Import run 2026-11-23 18:52:43

Owner: Jordan; pets: Biscuit, Mochi

Input:
```
Walk the dog at 8am for 30 minutes, then feed the cat at noon
```

### Attempt 1 (initial parse)

LLM call failed: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}}

### Final outcome

0 added, 1 rejected, 1 attempt(s)

- rejected: LLM call failed: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}}

### Import run 2026-11-23 18:53:17

Owner: Jordan; pets: Biscuit, Mochi

Input:
```
Walk the dog at 8am for 30 minutes, then feed the cat at noon
```

### Attempt 1 (initial parse)

Prompt summary: initial parse, 172 chars

Raw response:
```
[{"pet":"Biscuit","title":"Walk Biscuit","duration_minutes":30,"priority":"medium","frequency":"daily","weekday":null,"fixed_time":"08:00","confidence":0.95},{"pet":"Mochi","title":"Feed Mochi","duration_minutes":15,"priority":"high","frequency":"daily","weekday":null,"fixed_time":"12:00","confidence":0.95}]
```

Validation errors:
- item 1 ('Walk Biscuit'): conflict: Mochi and Biscuit overlap: Breakfast runs 08:00-08:10 but Walk Biscuit starts 08:00

### Attempt 2 (retry 1 with 1 error(s))

LLM call failed: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}}

### Final outcome

1 added, 1 rejected, 2 attempt(s)

- added: Feed Mochi (Mochi, confidence 0.95)
- rejected: item 1 ('Walk Biscuit'): conflict: Mochi and Biscuit overlap: Breakfast runs 08:00-08:10 but Walk Biscuit starts 08:00

