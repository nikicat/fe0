# Fe-in-Fe: a Fe-subset compiler written in Fe

Fe Builders Challenge 2026. Build window Nov 3–24 (UTC), register by Nov 17.

## 0. Scope: confirmed in scope (Oct 27, by email from the Fe team)

- The "pure compiler contributions" clause only excludes changes to the Rust codebases
  (fe, sonatina). The wording will be clarified and the judges told.
- Fixes and ergonomic PRs to the Rust compiler are welcome as a side effect, but they are not
  the entry.
- The Fe team has half-seriously considered a rewrite of Fe in Fe, and separately a
  **Fe subset suitable for formalizing in Lean**. Fe0's spec should be written with that in
  mind: small, explicit semantics, no undefined corners.
- Native-pipeline improvements land on master in the next few days, and they suggest
  experimenting with a master build.
  - The submission still needs a *release* of 26.5.0 or later; hopefully one is cut before
    Nov 3. Pin the exact version in the README.

## 1. Spike results (Oct 27, Fe 26.5.0, pre-window, throwaway)

`spike-lexer/`: a ~180-line lexer that reads source through the `std::io::Read` effect.

- **The same code runs natively and on the EVM.** The native build gets `with (Read = host())`,
  and `fe test` gets an `ArrayReader` over a byte array. Both work, and no compiler bugs were hit.
- **Native speed:** a 42 KB std file lexes in about 5 ms.
- **EVM gas:** about 803k gas per 1 KB of source at -O1/-O2 (784 gas/byte), and 1.42M at -O0.
- **Bytecode size:** the lexer plus a dispatcher is 3.1 KB of runtime code.
  - A full compiler would be roughly 8–15× that, so it will **exceed the 24 KB EIP-170 limit**.
    It has to be split across several contracts (see §4).
- **Language idioms learned:**
  - Mutable locals are `var`, not `let mut`. There is no `loop`, so use `while true`.
  - `as` only allows lossless casts. Narrowing needs `.downcast_truncate()` or `.downcast()`.
  - `xs[i]` on a `MemVec` yields an *access*. A non-Copy element needs `let t = ref xs[i]`,
    and `.get(i).unwrap()` cannot be used as a value.
  - Recursive types only work through raw `*T` (unsafe). Use an index-based arena for the AST.
  - No byte or char literals were found yet; keywords were matched with numeric arrays. Check
    whether `"fn".as_bytes()` indexing (`PackedBytes`) works.

**Rerun on master** (`d217a51bf`, Oct 27; built at `~/src/fe/target/release/fe` with
`--features cranelift`):
- Results are identical: the test passes, gas is 802,865 per KB at -O1/-O2, runtime code is
  3,144 bytes, and the native output matches.
- `--version` still says 26.5.0, so the native-pipeline improvements the Fe team mentioned have
  not landed yet.
- Rebuild with `git -C ~/src/fe fetch --depth 1 origin master && git -C ~/src/fe checkout -B master FETCH_HEAD && cargo build --release -p fe --features cranelift`.
- Rerun the spike after each rebuild.

## 2. How the official compiler is built (for reference)

Everything below is in `~/src/fe`.

- **Pipeline:**
  - `crates/parser`: a logos lexer (about 72 token kinds) and a hand-written recursive-descent
    parser with error recovery, building a rowan CST.
  - `crates/hir`: lowering, name resolution, type checking, **effects**, borrow checking.
  - `crates/mir`, then `crates/codegen`: Sonatina IR, then EVM bytecode. There is no Yul;
    the native backend uses cranelift.
- **Grammar:** there is no spec. The closest thing is `crates/tree-sitter-fe/grammar.js`
  (1456 lines) together with `parser/src/parser/*.rs`.
- **Dispatcher shape** (`mir/src/runtime/synthetic.rs:745`):
  1. If `calldatasize < 4`, go to the default arm.
  2. Compute `selector = calldataload(0) >> 224` and switch over the arms, sorted.
  3. Each arm ABI-decodes its arguments, runs the body and returns the encoded result.
  4. The default arm reverts with empty data, or runs the fallback arm if there is one.
- **Tests:**
  - dir-test plus insta snapshots, about 1,946 fixtures.
  - `crates/fe/tests/fixtures/fe_test/`: 270 self-checking `#[test]` files run through revm
    (pass or fail is the oracle).
  - Differential tests against solc: `fe/tests/differential_deposit.rs`.
  - 32 crash-regression files. No fuzzing.
- **Process:** `newsfragments/<issue>.<type>.md`, and release notes are built with eisenbote,
  a release-notes tool written in Fe.
- **Prior art:** none found for a Fe compiler written in Fe, any self-hosted EVM-language
  compiler, or an on-chain compiler that CREATEs its output. The closest are Brainfuck and Lisp
  interpreters written in Solidity. (Unverified: Fe Zulip and Paradigm/Curta CTF one-offs.)

## 3. Scope: the language subset ("Fe0")

Fe0 must be a strict subset of Fe: every Fe0 program is also a valid Fe program with the same behaviour.

- **Types:** `u256`, `bool`, `Address`.
- **Items:** `fn` (no generics), `const`, one `contract` with plain storage fields, a `msg`
  with `#[selector = 0x...]`, `init`, and `recv`.
  - `sol("...")` needs keccak at Fe0's own run time, which the native backend lacks.
  - Plan: a `Hasher` effect, with the opcode on the EVM and a software keccak-f[1600] written in
    Fe natively. It's a stretch goal after literal selectors work (see TODO §1).
- **Statements and expressions:**
  - `let`, `var`, `=`, `+=` and friends, `if`/`else`, `while`, `return`, calls;
  - arithmetic, comparison, bitwise and logical operators, checked overflow (panics like Fe);
  - `assert!`.
- **Effects:** `uses (field, mut field, ctx)` on handlers and functions. **Fe0 checks them**:
  reading an undeclared field or writing a non-`mut` field is an error. This is the
  Fe-specific highlight; most toy compilers skip it.
- **Left out:** traits, generics, structs and enums beyond storage, references and borrows,
  events (stretch), `StorageMap` (stretch, since keccak slot derivation is needed), and
  dynamic ABI types.

## 4. Architecture

```
source ──Source effect──▶ lexer ─▶ parser ─▶ arena AST (MemVec<Node>, u32 ids)
       ─▶ resolve + typecheck + effect check ─▶ codegen (AST → EVM ops, labels)
       ─▶ assembler (jump fixups, PUSH sizing) ─▶ initcode + runtime ─▶ Write effect / Bytes
```

- **Input and output are effects.** DESIGN.md §2 describes the `Source` input effect.
  - Natively, source comes from stdin (`host()`) and bytecode goes to stdout as hex.
  - On chain, `io::bytes` gives a `Source` over calldata `Bytes`. The output is a `MemVec<u8>`.
  - Under `fe test`, `io::text` gives a `Source` over a string.
  - The compiler core has no idea which one it is running under.
- **Errors:** report the first error with a position (no recovery). The lexer reports its error
  in `Lexed.err`.
- **Code generation:** emit EVM opcodes directly from the AST as a stack machine, with no IR.
  - Locals live in memory at fixed offsets per frame.
  - Function calls push a return label and jump; there is no recursion depth check, which is
    acceptable for the subset.
  - Storage fields get slots 0, 1, 2… in declaration order, matching Fe's layout for plain fields.
    Verify this differentially.
- **On chain** (24 KB limit):
  - Three contracts: `Frontend` (lex, parse, check, returning a serialised AST), `Backend`
    (code generation and assembly), and a `Compiler` facade that STATICCALLs both and then
    `create_raw` deploys the result.
  - Measure the size of each phase early. If one phase alone exceeds 24 KB, split it again.
- **SP1 (stretch):** prove that bytecode B was compiled from source S, a trustless version of
  source verification. Only if the SP1 target can take byte input.

## 5. Testing strategy (30% of the score is technical quality)

1. **Unit tests per phase** with `fe test` and `io::text` sources: tokens, AST shape, type and
   effect errors, assembler fixups.
2. **Differential testing against the official compiler**, entirely inside `fe test`:
   - Each corpus program `P.fe` is compiled normally (`evm.create2<P>`). A script also embeds
     its source as a `[u8; N]` constant.
   - The test runs Fe0 *on the EVM* on that source, deploys the result with `create_raw`,
     sends both contracts the same messages, and asserts identical return data, revert
     behaviour and storage reads.
   - So every test also exercises the compiler running on chain.
3. **Corpus:**
   - About 40 Fe0 programs written for this project (arithmetic, control flow, storage,
     effects, ABI).
   - The official fixtures contribute only 4 files (`bitnot`, `bool_literal`, and two
     immutable-field contracts for when immutables are supported). See corpus/SCAN.md.
   - The probes in `spike-conform/` (arithmetic edge cases, malformed calldata) seed the
     hand-written set.
4. **Negative tests:** programs that must be rejected (effect violations, type errors), with
   the expected error code and position.
5. **Native round trip:** `fefe < P.fe` produces hex, which is compared byte for byte with the
   output of the on-chain `fe test` run.
6. **Gas and size report:** gas to compile each corpus program on the EVM, and bytecode size
   compared with the official compiler's output.
7. **CI:** the starter's workflow (`fe fmt --check`, `fe test`) plus a native build step.
8. **Core, no longer a stretch goal: a random generator of Fe0 programs** feeding the
   differential test, i.e. fuzzing, which the official repo has none of. The official corpus
   yields only 4 Fe0-compatible files (corpus/SCAN.md), so hand-written programs plus generated
   ones are the whole suite.
   - Generated programs cover expression trees over `u256`/`bool` with checked operators,
     `if`/`while`, locals, storage fields with `uses`, and multiple arms.
   - The oracle is the official compiler: identical status, return data and revert data.
   - The generator can be a Python supporting tool. A Fe version using the `Rng` effect would be
     a nice extra.

## 6. Schedule

Registered as project FE-001 on Oct 28. Work items live in `.tasks/`, with due dates and
dependencies. A milestone is reached when its "done means" holds, checked by CI where it can be.

| Due | Milestone | Tasks | Done means |
|---|---|---|---|
| Nov 5 | **M1 Parser** | T0002 ✓, T0003 | Every SPEC §3 rule and every `P` code has a test, passing in CI. The bytecode size of the lexer and parser is measured, and the on-chain split (DESIGN §8) is decided from it. |
| Nov 9 | **M2 Checker** | T0016, T0004 | Every SPEC §5–6 rule has an accept test and a reject test with its error code and position. Constants evaluate with checked arithmetic. A `uses` violation is rejected with an `E` code. |
| Nov 14 | **M3 Codegen** | T0005 | The SPEC §6 Counter compiles with Fe0 running on the EVM, deploys with `create_raw`, and returns the same data and storage as the official build. Panic payloads and the dispatcher's empty reverts match too. |
| Nov 18 | **M4 Proof** | T0006, T0007, T0008 | 40+ hand-written programs and the `corpus/reject/` set pass the differential harness in CI. Generated programs from a fixed seed range pass too. `fe0-cli` prints the same bytes as the on-chain compile. |
| Nov 21 | **M5 On chain** | T0009 | The Front/Back/Compiler contracts stay under 24 KB on anvil and are deployed to Sepolia. A script compiles a program by transaction, deploys the result and calls it. A recorded demo exists. |
| Nov 22 | **M6 Spec** | T0015 | SPEC.md has no open [V] item, or each one left is listed as a known gap. The Lean-formalizable subset is described in the README. |
| Nov 24 | **M7 Submitted** | T0010 | The repo is public, with a README, license, pinned Fe version, build and test instructions, demo and disclosures. The form is submitted with the exact commit. |

M3 is the critical point: M4 and M5 both depend on it. If M3 slips past Nov 16, cut the
generator (T0007) to a smoke run and keep the hand corpus and the on-chain demo.

## 7. Risks

Likelihood and impact are rated H, M or L.

| # | Risk | L | I | Mitigation |
|---|---|---|---|---|
| 1 | **Toolchain drift between master and the release.** We experiment on master (as the Fe team advises), but the submission must pin a *release* of 26.5.0 or later. Features or fixes we rely on might exist only on master | H | H | Freeze the toolchain on Nov 3: the newest release out by then. CI runs on the pinned release only. After each upstream merge, master is checked by hand: rebuild Fe, then run `tools/spikes.sh` and the fe0 tests. A CI job on master would build Fe from source on every push. Never depend on a feature that is master-only |
| 2 | **Language churn mid-window.** Fe changes fast; 26.5 alone changed reference semantics. A release during Nov 3–24 could break our code or invite a costly upgrade | M | M | Do not upgrade mid-window unless a blocking bug fix requires it. Note the reason in the README if we do |
| 3 | **Compiler bugs, especially in the native backend.** The Fe team expects us to hit some ("as I suspect you will"). The native backend is experimental | H | M | Keep the core target-agnostic, so the EVM path under `fe test` is always the primary oracle and the native build is a bonus. Reduce each bug to a minimal example and file it; fix it upstream if it's cheap (welcome, and good for usefulness); keep `WORKAROUNDS.md` |
| 4 | **Experts on the jury.** Two judges are Fe core developers with a personal interest in Fe-in-Fe and a Lean-formalizable subset. Claims of correctness or "strict subset" will be scrutinised | M | H | Claim only what the tests show. Write a precise Fe0 spec (grammar and semantics) and a frank limitations section. Every difference from Fe found by testing is either fixed or documented |
| 5 | **The idea is pre-empted or leaks.** The Fe team has considered Fe-in-Fe itself, and another contestant could choose something similar | L | M | Keep it private until submission (no public Zulip posts or public repo pushes before Nov 24; make the repo public at submission). Our differentiators are the on-chain compile-and-deploy and effect checking |
| 6 | **24 KB contract size limit.** The lexer alone is 3.1 KB, and the full compiler is estimated at 25–45 KB | H | M | Split into front-end and back-end contracts plus a facade. Measure each phase Nov 3–5. A further split is the fallback |
| 7 | **Gas for compiling on chain.** Lexing costs about 0.8M gas per KB; a full compile is guessed at 5–10× that (8–16M for a 2 KB program). EVM memory costs grow quadratically | M | M | Measure on Nov 5. If it exceeds a block, compile via a free read-only call (`eth_call`) and deploy the output in a separate step, or keep the demo programs small |
| 8 | **Storage layout or ABI mismatch with official Fe** | M | M | Differential tests catch it; mirror the official dispatcher (`mir/src/runtime/synthetic.rs:745`) |
| 9 | **Scope creep.** Fe0 features, the Lean angle, SP1, fuzzing | H | H | Freeze Fe0 before Nov 3. The Lean subset is mentioned in the README only, with no formal work. Stretch items (SP1, fuzzing, events, `StorageMap`) only after the differential tests are green, and in that order |
| 10 | **Judges can't reproduce the native build.** It ships prebuilt only for x86-64 Linux and AArch64 macOS | M | L | The reproducible demo is `fe test` (EVM, works on every platform) plus a Sepolia deployment. Native instructions state which platforms are supported |
| 11 | **Missing the registration deadline** (Nov 17, firm) | L | H | Register as soon as the toolchain is frozen, by Nov 10 at the latest |
| 12 | **Pre-window work counted against us.** Only work done in the window is judged | L | M | Treat the Oct 27 spike as throwaway. Declare it and the plan as pre-existing work in the submission |
| 13 | **SP1 stretch is blocked.** The `sp1` feature is opt-in and not in the release binaries, and input support is unclear | M | L | Strictly a stretch goal; dropping it costs nothing in the core plan |
