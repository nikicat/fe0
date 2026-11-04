# 3. Write our own corpus and a random program generator

- Date: 2026-10-28 (pre-window)
- Status: accepted

## Context
The plan was to reuse the official test fixtures as the differential corpus.
`tools/corpus_scan.py` went through them (526 files on master, corpus/SCAN.md). After a manual
check only 4 fit Fe0: `code_backed_scalar_field.fe`, `immutable_contract_field_init_set.fe`,
`bitnot.fe` and `bool_literal.fe`. The official tests exercise what Fe0 leaves out: structs and
traits (365 files), method calls (332), arrays (143), generics (109) and the small integer
types.

## Decision
The corpus is written for this project: about 40 hand-written programs plus `corpus/reject/`.
A random Fe0 program generator (`tools/gen.py`, DESIGN.md §11) moves from stretch goal to core.
The official compiler is the oracle for both.

## Alternatives
- **Port official fixtures by hand:** each port would drop what makes the fixture interesting,
  and they would still not cover Fe0's own corners (`uses` checks, checked arithmetic at
  256 bits).

## Consequences
- The official repository has no fuzzing, so the generator is also something to offer back.
- Throughput matters: the harness runs batch ingots of about 25 programs (DESIGN.md §11).
