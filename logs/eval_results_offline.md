# PawPal+ evaluation (offline FakeLLM, 2026-11-23 19:29)

## Schedule import agent

| #  | Case                       | Added | Rejected | Attempts | Avg conf | Result | Notes |
|----|----------------------------|-------|----------|----------|----------|--------|-------|
| 1  | clean two-task import      | 2     | 0        | 1        | 0.90     | PASS   | ok    |
| 2  | weekly task with weekday   | 1     | 0        | 1        | 0.90     | PASS   | ok    |
| 3  | species word mapped to pet | 1     | 0        | 1        | 0.80     | PASS   | ok    |
| 4  | vague flexible task        | 1     | 0        | 1        | 0.70     | PASS   | ok    |
| 5  | unknown pet refused        | 0     | 1        | 3        | -        | PASS   | ok    |
| 6  | clash with existing task   | 0     | 1        | 3        | -        | PASS   | ok    |
| 7  | outside the day window     | 0     | 1        | 3        | -        | PASS   | ok    |
| 8  | empty input (guardrail)    | 0     | 1        | 0        | -        | PASS   | ok    |
| 9  | prompt injection stripped  | 1     | 1        | 3        | 0.90     | PASS   | ok    |
| 10 | invalid JSON then recovery | 1     | 0        | 3        | 0.90     | PASS   | ok    |

## Music RAG

| # | Task                   | Vibe                   | Picks              | Grounded | Result | Notes                                                                |
|---|------------------------|------------------------|--------------------|----------|--------|----------------------------------------------------------------------|
| 1 | Bath for Biscuit       | bath                   | Three Little Birds | yes      | PASS   | ok                                                                   |
| 2 | Play fetch in the yard | play / fetch           | Don't Stop Me Now  | yes      | PASS   | ok                                                                   |
| 3 | Give Mochi her pill    | medication / vet visit | Weightless         | yes      | PASS   | ok                                                                   |
| 4 | Morning walk           | walk                   | Riptide            | yes      | PASS   | dropped: Thunderstruck (not a retrieved candidate, not in songs.csv) |

## Summary

- Import agent: 10/10 passed
- Music RAG: 4/4 passed
- Overall: 14/14 passed
- Average confidence of added tasks: 0.86 (7 tasks)
