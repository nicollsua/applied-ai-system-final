# PawPal+ evaluation (live Gemini, 2026-11-23 19:20)

## Schedule import agent

| # | Case                       | Added | Rejected | Attempts | Avg conf | Result | Notes |
|---|----------------------------|-------|----------|----------|----------|--------|-------|
| 1 | clean two-task import      | 2     | 0        | 1        | 0.95     | PASS   | ok    |
| 2 | weekly task with weekday   | 1     | 0        | 1        | 0.98     | PASS   | ok    |
| 3 | species word mapped to pet | 1     | 0        | 1        | 0.95     | PASS   | ok    |
| 4 | vague flexible task        | 1     | 0        | 1        | 0.95     | PASS   | ok    |
| 5 | unknown pet refused        | 0     | 1        | 1        | -        | PASS   | ok    |
| 6 | clash with existing task   | 0     | 1        | 3        | -        | PASS   | ok    |
| 7 | outside the day window     | 0     | 1        | 3        | -        | PASS   | ok    |
| 8 | empty input (guardrail)    | 0     | 1        | 0        | -        | PASS   | ok    |
| 9 | prompt injection stripped  | 1     | 0        | 1        | 0.95     | PASS   | ok    |

## Music RAG

| # | Task                   | Vibe                   | Picks                     | Grounded | Result | Notes              |
|---|------------------------|------------------------|---------------------------|----------|--------|--------------------|
| 1 | Bath for Biscuit       | bath                   | Three Little Birds        | yes      | PASS   | retrieval fallback |
| 2 | Play fetch in the yard | play / fetch           | Don't Stop Me Now         | yes      | PASS   | retrieval fallback |
| 3 | Give Mochi her pill    | medication / vet visit | Weightless, Clair de Lune | yes      | PASS   | ok                 |
| 4 | Morning walk           | walk                   | Riptide                   | yes      | PASS   | retrieval fallback |

## Summary

- Import agent: 9/9 passed
- Music RAG: 4/4 passed
- Overall: 13/13 passed
- Average confidence of added tasks: 0.95 (6 tasks)
