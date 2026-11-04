---
status: todo
deps: [T0005]
due: 2026-11-18
tags: [testing]
---
# Differential harness and a 40+ program corpus

## Goal
`tools/embed.py` and the batch-ingot harness from DESIGN.md §10–11: each corpus program is built
by the official compiler and by Fe0 running on the EVM, then both get the same calls and must
return identical bytes. Corpus of 40+ hand-written programs plus `corpus/reject/` negative tests.

## Decisions
- Batches of about 25 programs per ingot, run with `fe test --jobs 0` (18 s per 200).
- Every contract gets a unique name (argotorg/fe#1887 is fixed only on master).
- Assert Fe0's runtime code ≤ 24,576 bytes; the test EVM does not enforce it.
