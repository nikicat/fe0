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
- [x] Official compiler's storage slots for plain fields, its return data and revert data, and
      its overflow panic codes. Fe0's output must match them exactly
      **Results** (`spike-layout/`, master `d217a51bf`, from `fe test --trace-evm` and revert payloads):
      - **Storage:** one 32-byte slot per plain field, in declaration order, starting at 0, with
        **no packing**. Fields `u256 a, bool b, Address c, u256 d` → slots 0, 1, 2, 3; `true`
        is stored as 1.
      - **Return data:** standard ABI, one 32-byte word (`bool` true → 32 bytes holding `1`).
      - **Overflow and underflow:** `Panic(0x11)`, i.e. `0x4e487b71` followed by the code word.
        **Division by zero:** `Panic(0x12)`. **`assert!(false)`:** `Panic(0x01)`.
      - **`assert!(false, "nope")`:** Solidity `Error(string)` (`0x08c379a0` + ABI string).
      - **Unknown selector:** revert with empty data.
      - All of this matches Solidity's conventions, so Fe0 codegen can emit exactly these payloads.
- [x] Passing `Bytes` from one contract to another and back, and supplying `Read` from calldata.
      Needed for splitting the on-chain compiler across contracts (24 KB limit)
      **Yes** (`spike-lexer/src/split.fe`):
      - A `Front` contract takes `Lex { src: Bytes } -> Bytes` and feeds the calldata `Bytes`
        through a `BytesReader: Read` into the unchanged lexer.
      - A `Facade` contract (`uses (call: mut Call)`) forwards to `Front` and returns its `Bytes`.
        Both a direct call and a call through the facade pass.
      - Build values with `Bytes::from_payload(source: memvec.into_array().span())`, and read
        them with `.len()` and `.byte_at(i)`.
- [x] Is keccak available natively (for `sol("...")` selectors)? Do byte or string literals
      exist that can be indexed (for keyword matching in the lexer)?
      **Keccak: only on the EVM, or when the input is a compile-time constant.**
      - `core::keccak` (an intrinsic) and `std::evm::keccak256(MemSpan)` both fail to lower
        natively ("target does not support EvmKeccak256").
      - A first native probe seemed to work only because the input was constant and the hash was
        computed at compile time (`spike-native/probe_keccak.fe`).
      - **Consequence for Fe0:** make hashing an effect (`uses (h: Hasher)`). The EVM provider
        uses the KECCAK256 opcode; the native provider is a software keccak-f[1600] in Fe (about
        150 lines), differential-tested against the opcode under `fe test`.
      - Fallback: Fe0 v1 accepts only literal `#[selector = 0x...]`, with `sol("...")` as stretch.
      **Literals:** there are no byte or char literals (`b'a'` is a parse error).
      - A typed string works: `let s: String<2> = "fn"`, then `s.as_bytes()[i]` (a
        `PackedBytes`) indexes at run time natively.
      - An *untyped* `"fn".as_bytes()` becomes `Bytes`, which has no `Index`; use `.byte_at(i)`
        instead. Keyword tables can be typed `String<N>` constants.

## 2. Freeze the Fe0 specification

- [x] Grammar (EBNF): [SPEC.md](SPEC.md) draft 0. The example compiles and passes under the
      official compiler (`spike-spec/`)
- [x] Semantics: overflow, evaluation order, storage slot assignment, effects. Drafted; open
      points are marked [V] in SPEC.md, with §9 listing the open questions
- [x] Check every rule against the official compiler (ties into §1)
      Done in `spike-conform/`: 23 compile-time probes in `compile/*.fe` (checked with
      `fe check --standalone`) and 15 run-time probes in `src/tests.fe`.
      - SPEC.md now has 34 [✓] marks and 3 open [V] items: the newline rule, `init` with bad
        arguments, and `Address` storage alignment.
      - Where Fe turned out more permissive (forward const references, `{` on the next line,
        locals shadowing fields, duplicate `uses`, `init`/`recv` as names), Fe0 stays strict,
        which the subset rule allows.
- [ ] Keep it small and explicit, Lean-formalizable (as the Fe team asked)

## 3. Pick the test corpus

- [x] Go through `crates/fe/tests/fixtures/fe_test/` (270 programs) and
      `crates/codegen/tests/fixtures/` (117 programs)
      Master now has 526 files. `tools/corpus_scan.py` → [corpus/SCAN.md](corpus/SCAN.md)
- [x] List the programs that are Fe0-compatible as they are or with small edits
      **Verdict: the official corpus is almost useless as a Fe0 differential suite.**
      - After a manual check, only 4 files fit: `code_backed_scalar_field.fe`,
        `immutable_contract_field_init_set.fe`, `bitnot.fe`, `bool_literal.fe`.
      - Even the two contracts use non-`mut` fields, which Fe0 v1 excludes; see the next point.
      - The official tests exercise exactly what Fe0 leaves out: structs and traits (365 files),
        method calls (332), arrays (143), generics (109), `u8`–`u64` types.
      - **Side finding:** non-`mut` contract fields are code-backed immutables, not storage.
        SPEC.md §6 is updated and Fe0 v1 requires `mut` on every field.
      - **Consequence:** we write the corpus ourselves, and a **random Fe0 program generator**
        moves from stretch goal to core (PLAN.md §5).

## 4. Setup (outward-facing steps need the user's go-ahead)

- [x] Private GitHub repository: <https://github.com/nikicat/fe-contest>, created Oct 28 and
      pushed. It must be made public at submission (an OSI license is required by then).
- [ ] CI, pinned to the frozen Fe release. Add it on Nov 3 with the real project: today's spikes
      have tests that fail on purpose (`lex_gas`, the probes in `spike-conform`), so CI on them
      would always be red
- [ ] Register early with a vague title (e.g. "Fe developer tooling"). Deadline Nov 17
- [ ] Optional: office hours, Thursday Oct 30 at 16:00 UTC. Don't mention the idea

## 5. Watch Fe master

- [ ] Check for the native-pipeline merge every couple of days, then rebuild
      (`cargo build --release -p fe --features cranelift` in `~/src/fe`) and rerun
      **`tools/spikes.sh [fe-binary]`**. It re-checks all 54 recorded spike and probe values
      and prints only the differences; gas is compared within ±5%.
      - Oct 28: master `f4046d212` (PR #1877, native frame-scoped objects, plus a Sonatina
        update) and release 26.5.0 both reproduce everything. Lexer gas went from 802,865 to
        803,236.
- [x] On Nov 3, freeze the toolchain on the newest release
      **Frozen on Fe 26.5.1** (released Oct 28; it only fixes a parser hang). `tools/spikes.sh`
      reproduces all 54 recorded values on it.
      - CI (`.github/workflows/ci.yml`) downloads exactly that release.
      - Master has since fixed both of our issues: #1887 via #1890, and #1886 via #1909, which
        adds native keccak. Neither blocks us, so we don't upgrade mid-window (PLAN risk 2).
- Open upstream PRs to watch (as of Oct 28), all by sbillig:
  - **#1883 "Native portability, panics and tests"**: probably the native work the Fe team
    mentioned. Native `usize` becomes 64-bit, so check the spike's `usize` arithmetic after it
    lands. `keccak_words` sits in its list of fixtures excluded from native runs, so native
    keccak stays unsupported.
  - **#1882 "Resolve arithmetic mode at the operator"**: could change checked-arithmetic
    semantics. Rerun the `spike-conform` run-time probes after it lands.
  - **#1845 "Match fieldless msg variants by path without `{}`"**: Fe0 always writes `Name {}`,
    which should stay valid. Recheck the spec example after it lands.
  - **#1878 "Per-function code sizes with `--emit sizes`"**: useful for the 24 KB measurement
    on Nov 3–5.

## Planned by unsmell run 20261104-190143

- [ ] **End of input is the byte value -1** (`fe0/src/io.fe` `Source::next_byte -> i32`,
      `fe0/src/lexer.fe` `Lexer.peeked: i32`, compared as `< 0` at several sites).
      A `-1` could be pushed into the source buffer as byte 255 if a caller forgets the check.
      - Fix: `next_byte() -> Option<u8>` and `peeked: Option<u8>`, so the end of input is not
        a byte value at all.
      - First measure the cost: the lexer runs at about 800 gas per source byte on the EVM, and
        an `Option` on every byte may add a noticeable share. Measure with `spike-lexer`'s
        `lex_gas` pattern (DESIGN.md §8a), then decide.
      - Findings b1-21, b2-6, x-3 in `.git/unsmell/20261104-190143/`.
