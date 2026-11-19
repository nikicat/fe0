# 3. Write our own corpus and a random program generator

- Date: 2026-10-28 (pre-window)
- Status: accepted

## Context
The official test fixtures are the obvious differential corpus. `tools/corpus_scan.py` goes
through them (526 files on master, corpus/SCAN.md), and after a manual check only 4 fit Fe0:
`code_backed_scalar_field.fe`, `immutable_contract_field_init_set.fe`, `bitnot.fe` and
`bool_literal.fe`. The official tests exercise what Fe0 leaves out: structs and traits (365
files), method calls (332), arrays (143), generics (109) and the small integer types.

## Decision
The corpus is written for this project: hand-written programs plus `corpus/reject/`. A random
Fe0 program generator (`tools/gen.py`, DESIGN.md §11) is core work, not a stretch goal. The
official compiler is the oracle for both.

The harness runs the programs in batch ingots of about 25, with one test per batch ingot
(see Measurements).

## Alternatives
- **Port official fixtures by hand:** each port would drop what makes the fixture interesting,
  and they would still not cover Fe0's own corners (`uses` checks, checked arithmetic at
  256 bits).
- **Standalone files, one per program:** they cannot depend on the `fe0` ingot.
- **One test per program:** on the EVM backend, `fe test` compiles each test alone, with the
  whole compiler in it. The cost follows the number of tests, not the number of programs
  ([WORKAROUNDS.md](../WORKAROUNDS.md#open-bugs)).
- **`fe test --grouped`:** does not help (see Measurements).

## Consequences
- The official repository has no fuzzing, so the generator is also something to offer back.
- Reject tests run on `--backend native`, which builds them all into one executable.

## Measurements
On 8 cores, with Fe 26.5.x. First, 200 small contracts of 3 recv arms each, with no call
into Fe0:

| Layout | Time for 200 |
|---|---|
| One ingot | 35.4 s (~175 ms each) |
| 200 standalone files, `--jobs 0` | 39.7 s |
| Same, `--jobs 1` | 96 s |
| **8 ingots × 25, `--jobs 0`** | **18.4 s** |

Then with tests that call Fe0's in-EVM compile:

| Run, at `-O 1` | One test per program | One test per batch ingot |
|---|---|---|
| batch01, 25 programs | 101 s | 12.4 s |
| `tools/gen.py -n 25` | 98 s | 14.7 s |

- 70 reject tests take 142 s on the EVM backend and 4.7 s on `--backend native`.
- `fe test --grouped` does not help: 98 s against 101 s.
