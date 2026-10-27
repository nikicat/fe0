# TODO before the build window (Oct 28 – Nov 2)

Only work done in the window (Nov 3–24) is judged. Work done now is design and checking
unknowns, declared as pre-existing. See [PLAN.md](PLAN.md).

## 1. Check the unknowns (throwaway experiments, under 1h each)

- [x] Can `fe test` deploy hand-written bytecode with `create_raw` and call it? Try a contract
      that just returns 42. Every differential test depends on this
      **Yes, on 26.5.0 and master** (`spike-lexer/src/create_raw.fe`):
      - Hand-assembled initcode deploys, and a raw call returns the 32-byte word 42.
      - A typed `evm.call` through a `msg` decodes 42 from the same contract.
      - Invalid initcode gives address 0 without reverting, so a test can detect a failed deploy.
      - Bytecode is built as `MemVec<u8>` → `.into_array().span()` (MemVec has no `span()`).
        A `MemArray<u8>` is byte-packed.
- [ ] Official compiler's storage slots for plain fields, its return data and revert data, and
      its overflow panic codes. Fe0's output must match them exactly
- [ ] Passing `Bytes` from one contract to another and back, and supplying `Read` from calldata.
      Needed for splitting the on-chain compiler across contracts (24 KB limit)
- [ ] Is keccak available natively (for `sol("...")` selectors)? Do byte or string literals
      exist that can be indexed (for keyword matching in the lexer)?

## 2. Freeze the Fe0 specification

- [ ] Grammar (EBNF)
- [ ] Semantics: overflow, evaluation order, storage slot assignment, effects
- [ ] Check every rule against the official compiler (ties into §1)
- [ ] Keep it small and explicit, Lean-formalizable (as the Fe team asked)

## 3. Pick the test corpus

- [ ] Go through `crates/fe/tests/fixtures/fe_test/` (270 programs) and
      `crates/codegen/tests/fixtures/` (117 programs)
- [ ] List the programs that are Fe0-compatible as they are or with small edits

## 4. Setup (outward-facing steps need the user's go-ahead)

- [ ] Private GitHub repository from the starter, with CI pinned to Fe 26.5.0
- [ ] Register early with a vague title (e.g. "Fe developer tooling"). Deadline Nov 17
- [ ] Optional: office hours, Thursday Oct 30 at 16:00 UTC. Don't mention the idea

## 5. Watch Fe master

- [ ] Check for the native-pipeline merge every couple of days, then rebuild
      (`cargo build --release -p fe --features cranelift` in `~/src/fe`) and rerun the spike
- [ ] On Nov 3, freeze the toolchain on the newest release
