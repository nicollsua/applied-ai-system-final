# PawPal+ evaluation (offline FakeLLM, 2026-11-23 20:40)

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

## Retrieval impact (candidates inside the task's energy range)

Baseline = title words vs songs.csv tags only. Multi-source = vibe from vibes.md (+ synonyms) then songs.csv scored by tags, energy and mood.

| Task                   | Target energy | Baseline | Multi-source RAG |
|------------------------|---------------|----------|------------------|
| Give Mochi her pill    | 1-2           | 0/5      | 5/5              |
| Bath for Biscuit       | 1-4           | 4/5      | 5/5              |
| Play fetch in the yard | 8-10          | 5/5      | 5/5              |
| Brush Mochi            | 2-4           | 0/5      | 5/5              |
| Scoop litter box       | 6-9           | 3/5      | 5/5              |

## Summary

- Import agent: 10/10 passed
- Music RAG: 4/4 passed
- Overall: 14/14 passed
- Average confidence of added tasks: 0.86 (7 tasks)
- Retrieval: 12/25 candidates in range with the baseline, 25/25 with multi-source RAG
