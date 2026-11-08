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
- Throughput matters: the harness runs batch ingots of about 25 programs (see Measurements).

## Measurements
Measured on Oct 28 on 8 cores, with 200 small contracts of 3 recv arms each. Fe0's in-EVM
compile did not exist yet.

| Layout | Time for 200 |
|---|---|
| One ingot | 35.4 s (~175 ms each) |
| 200 standalone files, `--jobs 0` | 39.7 s |
| Same, `--jobs 1` | 96 s |
| **8 ingots × 25, `--jobs 0`** | **18.4 s** |

- Standalone files cannot depend on the `fe0` ingot, so they are not an option for the harness.

Measured again on Nov 8 on 8 cores, after Fe0's in-EVM compile existed. The cost follows the
number of tests, not the number of programs.
[WORKAROUNDS.md](../WORKAROUNDS.md#open-bugs-2651) says why.

| Run, at `-O 1` | One test per program | One test per batch ingot |
|---|---|---|
| batch01, 25 programs | 101 s | 12.4 s |
| `tools/embed.py`, 44 programs and 70 reject programs | 4 min 22 s | 26 s |
| `tools/gen.py -n 25` | 98 s | 14.7 s |

- The 70 reject tests take 142 s on the EVM backend and 4.7 s on `--backend native`.
- `fe test --grouped` does not help (98 s against 101 s).
