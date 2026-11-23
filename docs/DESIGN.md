# Fe0 compiler design

How the compiler is built. [SPEC.md](SPEC.md) defines what Fe0 means, [PLAN.md](PLAN.md) the
scope and schedule, and [docs/adr/](adr/README.md) the reasons for each choice. Rules:
- Prefer the simplest thing that is correct.
- The input programs are small (a few KB), so linear scans and fixed-size encodings are fine.
- Every shortcut is marked with a `ponytail:` comment in the code, naming its limit.

## 1. Repository layout

| Path | Holds |
|---|---|
| `fe0/` | the compiler as a library: no I/O, shared by every target |
| `fe0-cli/` | the native CLI: stdin to hex on stdout, errors on stderr (§9) |
| `fe0-chain/` | the compiler on chain: one contract per phase, plus Compiler (§8) |
| `registry/` | the registry of deployed programs and the list of Compilers it accepts (ADR 0031, ADR 0034) |
| `fe.toml` | a workspace of the compiler's and the registry's ingots, so that Fe's language server analyses only them, not every other `.fe` file as a standalone file |
| `corpus/` | test programs and call scripts; `reject/` must fail, `gen/` is generated (§10, §11) |
| `tools/` | the harnesses, generators and deploy scripts; each module's docstring says what it does |
| `spike-*/` | probes of the official compiler, which SPEC.md and the ADRs cite |
| `playground/` | a web page that compiles and deploys through the deployed compiler |
| `deployments/` | the addresses of the deployed compiler and registries, by chain id |
| `docs/` | this document, SPEC.md, PLAN.md, the ADRs, WORKAROUNDS.md and DEMO.md |
| `out/` | what the tools write; not committed |

## 2. Lexer

- **Input** comes one byte at a time through fe0's own `Source` effect, not std I/O
  ([ADR 0010](adr/0010-source-effect.md)). Tokens are spans of the source buffer it fills.
- **Integer literals:** the lexer checks only their syntax. The parser computes the value when
  it stores the literal, and reports `L004` there, so the first error in source order wins.
- **Keywords:** an identifier is packed into one word and looked up in a table of packed
  spellings, which keeps the Lexer small ([ADR 0014](adr/0014-contract-per-phase.md)).
- **Newlines:** where SPEC §3.4 keeps a newline token, the parser decides whether it ends a
  statement. Where it drops one, the lexer checks that the line break is allowed there.
- **Plain comments** make no tokens. A newline token's span carries where the last plain
  comment line after it starts ([ADR 0024](adr/0024-newline-span-carries-comment-line.md)).
- **Doc comments** are tokens, even inside `( )`. The parser skips them only where SPEC §1
  allows them, so a doc comment anywhere else is a syntax error.
- **Positions:** line and column are computed only when an error is reported.

## 3. AST: an index-based arena

The AST lives in flat arrays and refers to nodes by index, with 0 meaning "none"
([ADR 0005](adr/0005-arena-ast.md)). Ids, operators and written types are typed, so none of
them travels as a bare integer. Check results go in side tables indexed by node, which cross
to Back with the AST (§8). The AST's nodes are never mutated after parsing.

## 4. Parser

- Recursive descent, one function per grammar rule of SPEC §3.1, with precedence climbing for
  binary expressions.
- **No error recovery** ([ADR 0006](adr/0006-no-error-recovery.md)): the first error ends the
  parse, and `parse()` reports it in a field, not a `Result`
  ([ADR 0011](adr/0011-error-field-not-result.md)).
- **Recursion is bounded:** nesting depth is capped at `MAX_DEPTH`
  ([ADR 0012](adr/0012-max-depth.md)).

## 5. Checker

- **Constants** are evaluated before any body, in passes over the items, with the same checked
  arithmetic as run time ([ADR 0025](adr/0025-constants-in-passes.md)).
- **Return paths:** a body that ends in `return` on every path has the type `TY_NEVER`, which
  fits any type. So no separate "always returns" analysis is needed.
- **Effects are contract fields** with no storage. So the name rules and the unused-entry
  warning cover them with no extra code ([ADR 0017](adr/0017-caller.md)).
- **Events:** the checker records each event's topic 0 and the word of each field, so code
  generation needs neither the source nor keccak ([ADR 0019](adr/0019-events.md)).
- **Calls:** a call's resolved variant gives code generation its selector, field order and
  return type, so a call adds no side table.
- **Recursion:** the checker recurses as the parser does, so `MAX_DEPTH` bounds it too
  (`check_tests::deep_nesting_and_long_chains`). An `else if` chain is checked in a loop.

## 6. Code generation

Opcodes are emitted straight from the AST, with no IR
([ADR 0007](adr/0007-codegen-from-ast.md)).

### 6.1 Memory layout

| Range | Use |
|---|---|
| `0x00–0x3f` | Scratch: return value, panic payload head, the key and slot that a map entry's slot is hashed from |
| `0x40` | A copy of **FP**, the current frame pointer |
| `0x60–0x7f` | Reserved (EVM convention, unused) |
| `0x80…` | Frames, growing upward. While `log.emit` runs, its data and topics are in the words past the current frame. While `a.call(…)` runs, its calldata is there |

Revert data is written from scratch onward and may run over FP's copy and the frames. This is
safe because `REVERT` follows at once.

**Frames.** A function's frame is `2 + params + locals` words: the caller's saved FP at
`[FP+0]`, the return address at `[FP+32]`, then the parameters and locals from `[FP+64]`. Every
local has a fixed slot, with no slot reuse ([ADR 0021](adr/0021-frames-gas-and-depth.md)).
`init` and the arms run in the first frame, at `0x80`, because nothing calls them. So their
code addresses their frame with constants.

**FP on the stack.** A function keeps its FP on the stack, under the words it pushes, and loads
the copy at `0x40` when FP sits too deep for `DUP16`
([ADR 0023](adr/0023-frame-pointer-on-the-stack.md)).

### 6.2 Calling convention

- **Caller:** evaluates the arguments onto the stack, stores them into the callee's frame at
  `FP + caller_frame_size`, with the return label and its own FP in the frame's head. It then
  sets the copy at `0x40` to the callee's FP, pushes that FP and jumps.
- **Callee on return:** brings its FP to the top, puts the saved FP back in the copy at `0x40`,
  and jumps to the return label. The result, if any, stays on the stack.

Gas bounds the memory cost of recursion, and the EVM stack bounds its depth
([ADR 0023](adr/0023-frame-pointer-on-the-stack.md)).

### 6.3 Expressions

Each expression leaves one word on the stack, or none if unit-typed. The differential tests of
§10 check the results against Fe, not the instructions.

| Construct | Emitted |
|---|---|
| Checked arithmetic | the operation, then a jump to the panic stub of its code on overflow or a zero divisor |
| `<< >>` | `SHL`/`SHR`, which take the shift amount on top |
| Comparisons | `b` is on top, so `a < b` is `GT` and `a > b` is `LT` |
| `log.emit(E { … })` | each value stored past the frame at its field's word, the indexed ones loaded back as topics, then `LOGn` |
| `a.call(M::V { … })` | calldata past the frame: the selector in word 0, so its 4 bytes end that word, and each value at word 1 plus its field's index. `CALL` from byte 28 with all gas and no value. A failed call reverts with its return data. A return value needs 32 bytes of return data and is checked as an arm checks an argument |

- **Stubs:** one shared block per panic code (`0x01`, `0x11`, `0x12`), one that reverts with
  empty data, and one that reverts with the failed call's return data. The initcode and the
  runtime code each hold their own copy of the stubs and functions they jump to.
- **Leaving early:** a function pops the words above its FP before it returns, and `break` and
  `continue` pop down to the loop's depth. Leftover words do not matter in arms and `init`.

### 6.4 Dispatcher (runtime entry)

It mirrors the official compiler's ([ADR 0002](adr/0002-match-official-output.md)):

```
CALLVALUE → JUMPI revert_empty         ; all arms are non-payable
CALLDATASIZE 4 LT → JUMPI revert_empty
0 CALLDATALOAD 224 SHR                  ; selector
for each arm: DUP1 PUSH4 sel EQ → JUMPI arm_k
revert_empty: 0 0 REVERT
```

Each arm checks `CALLDATASIZE >= 4 + 32n`, checks each argument word (`bool ≤ 1`,
`Address >> 160 == 0`) and stores it in its frame, runs the body, and returns the result
word, or stops for unit.

- One up-front `CALLVALUE` check is safe because every failing path reverts with empty data,
  so the order of checks is unobservable.
- The arms are a linear chain of `EQ`s ([ADR 0021](adr/0021-frames-gas-and-depth.md)).

### 6.5 Deployment layout

```
[ initcode ][ runtime ][ constructor args, appended by the deployer ]
```

The initcode rejects value, as the official initcode does, so the CREATE fails
(`init_with_value` in `spike-conform/src/init_args.fe`). It then checks
`CODESIZE >= init_len + rt_len + 32n`, copies the arguments into the `init` frame and checks
them as the dispatcher does, runs `init`, and returns the runtime. A contract without `init`
skips the arguments, so extra bytes after the runtime are ignored.

## 7. Assembler

Every jump pushes a 2-byte label, so assembly is one pass with no relaxation
([ADR 0026](adr/0026-two-byte-jump-labels.md)). The runtime code is assembled first, so that
the initcode can push its length.

## 8. On-chain split (24 KB limit)

The compiler does not fit the 24,576-byte limit, so each phase is its own contract
([ADR 0014](adr/0014-contract-per-phase.md)). The contracts are in `fe0-chain/`, and
[fe0-chain/README.md](../fe0-chain/README.md) gives Compiler's interface.

| Contract | Message | Does |
|---|---|---|
| `Lexer` | `lex(bytes src) -> uint256[]` | lex, then put the tokens |
| `Parser` | `parse(bytes src, uint256[] toks) -> uint256[]` | parse, then put the AST |
| `Checker` | `check(bytes src, uint256[] ast) -> uint256[]` | check, then put the checked program |
| `Back` | `generate(uint256[] ir) -> bytes` | generate and assemble, return the deploy code |
| `Compiler` | `compile`, `deploy`, `version` | `STATICCALL` each phase in turn |

- **Wire format:** each phase returns ABI `uint256[]`, in the format of `fe0/src/wire.fe`. The
  source does not cross. It is each phase's own `bytes` argument, so Back never sees it.
- **Errors:** a phase reverts with `CompileError` (`fe0/src/diag.fe`). Warnings do not
  cross (§9).
- **Trust:** a phase contract decodes its input without checks
  ([ADR 0027](adr/0027-phase-contracts-trust-input.md)).
- **Deployment:** one transaction ([ADR 0028](adr/0028-one-transaction-deploy.md)).
- **Build:** as Sourcify rebuilds it, at `-O 1`
  ([ADR 0033](adr/0033-verify-on-sourcify.md)).
- **Measured on Fe 26.7.0** by `tools/chain_check.py`:

  | Contract | Runtime bytes | Deploy gas |
  |---|---|---|
  | Lexer | 5,857 | 1.31M |
  | Parser | 18,175 | 3.98M |
  | Checker | 20,405 | 4.47M |
  | Back | 17,728 | 3.89M |
  | Compiler | 1,693 | 0.51M |

  Deploying all five costs 14.2M gas, and `deploy` of `counter.fe` 2.05M. Compiling costs up to
  27.7M gas, for `corpus/amm.fe` (8,141 bytes).

## 8a. Measured limits of the host (official Fe on the EVM)

- **Recursion depth is bounded by the 1,024-slot EVM stack, not by gas.** This bounds the
  parser ([ADR 0012](adr/0012-max-depth.md), with the measurements) and the code that Fe0
  generates ([ADR 0021](adr/0021-frames-gas-and-depth.md)).
- **`MemVec` growth is linear,** so the arena is affordable ([ADR 0005](adr/0005-arena-ast.md)).
- **`fe test` enforces neither EIP-170 nor EIP-3860, and anvil does.** WORKAROUNDS.md gives
  the measurements and how the tools check both limits.

## 9. Diagnostics

Every phase reports an error as a `Diag`, and `fe0/src/diag.fe` defines the codes. The messages
are a table in `fe0-cli/src/messages.fe`, because only the CLI prints them, so the on-chain
compiler does not pay for them in bytecode.

Inside the lexer, the parser and the checker, a function that can fail returns
`Result<Diag, T>`. The entry points report the error in a field instead
([ADR 0011](adr/0011-error-field-not-result.md)).

Warnings never stop the compile, so they come beside the result. They do not cross on chain,
since `compile` returns only the deploy code and `deploy` only an address.

## 10. Differential test harness

`tools/embed.py` writes each program into a batch ingot, as Fe code for the official compiler
and as a string literal. Its test calls `fe0/src/difftest.fe`, which, on the EVM:

1. compiles the string with the `fe0` library;
2. copies the official build out of the test's own code;
3. deploys both builds the same way, so that only their code can differ. A failed create gives
   address 0 rather than a revert (`spike-lexer/src/create_raw.fe`);
4. sends the script's calls and the dispatcher probes to both, and asserts that the success
   flags and return data are equal, revert data included;
5. asserts that Fe0's build fits EIP-170 and EIP-3860 (§8a).

A failed test reverts with a typed error that says what failed and where. `fegen.check_errors`
checks that `fe0/src/difftest.fe` and `tools/fegen.py` spell each error alike. The codegen
tests (`fe0/src/codegen_tests.fe`) are differential tests of the same kind.

**One test per batch.** Each batch ingot holds `BATCH` programs (`tools/embed.py`), and its root
module holds one test that calls every runner. When that test fails, the harness runs each
program's own test in that batch, to find the program that fails.
[ADR 0003](adr/0003-own-corpus-and-generator.md) says why programs are batched.
The reject tests run on the native backend ([WORKAROUNDS.md](WORKAROUNDS.md)).

**Gas and level.** Fe builds at its reference level, `-O 1` (`embed.REFERENCE_LEVEL`; SPEC.md,
the subset rule). A call gets
`CALL_GAS` inside `fe test` (`fe0/src/difftest.fe`) and `TX_GAS` on a node (`tools/node.py`).

**On a node.** Inside `fe test`, every call comes from the test contract, and logs are not
visible. `tools/node_check.py` ([ADR 0016](adr/0016-steps-toward-real-contracts.md), step 0)
runs the same call scripts on a local anvil node, from the accounts that the scripts name.
- A program whose script deploys another program to call, or names a deployment such as
  `@this`, runs only on a node, since a test inside `fe test` can do neither
  ([ADR 0020](adr/0020-external-calls.md)).
- Each build deploys its own build of each callee, from the same snapshot of the node. So both
  builds' contracts get the same addresses, and a slot hashed from one is the same in both.
- `node_check.py --levels` also compares Fe's other levels, for bugs in Fe. CI does not run it
  ([ADR 0029](adr/0029-levels-not-in-ci.md)).

**The native CLI.** The two targets share one library, so they must agree byte for byte.
`tools/cli_check.py` checks this on every program.

## 11. Random program generator (`tools/gen.py`)

It writes programs that both compilers accept and runs them through §10's harness
([ADR 0003](adr/0003-own-corpus-and-generator.md)). CI runs the fixed seeds 1 to 25, so a
failure never depends on chance. Each shape it avoids because Fe mishandles it is marked at the
code, with its task id or WORKAROUNDS.md entry.

## 11a. Mutation tester (`tools/mutate.py`)

gen.py's programs never test the rules by which Fe0 rejects a program. So the mutation tester
makes one change to an accepted program and checks that both compilers accept or reject the
mutant alike. Fe's verdict stands in for an `// expect:` line. A narrowing, a rule by which Fe0
rejects what Fe accepts, is stated in SPEC.md and shown by a reject program, its probe
(SPEC.md §8), and only a probe's code excuses Fe0's rejection. Mutations rewrite the program
text ([ADR 0030](adr/0030-mutations-on-text.md)); the tool's docstring gives the rest.

## 12. Hashing (`sol("…")` selectors, a stretch goal)

Selectors are literal first ([ADR 0004](adr/0004-literal-selectors-first.md)). The remaining
work is to parse `sol("…")` and take the first 4 bytes of the signature's hash, made with
`std::evm::crypto::keccak256` as for an event's topic 0 ([ADR 0019](adr/0019-events.md)), with
no `Hasher` effect ([ADR 0015](adr/0015-move-to-26-6-0.md)).

## 13. Testing per phase

| Phase | Tests |
|---|---|
| Lexer | Token streams for each token class; error positions |
| Parser | Node shapes for each grammar rule; a reject test for each `P` error |
| Checker | One accept and one reject or warning per rule of SPEC §2 and §4–6, with code and position (`tools/gen_check_tests.py`) |
| Codegen | Differential, as in §10 (`tools/gen_codegen_tests.py`) |
| Assembler | Pushes, and fixups of labels bound before and after their use |
| End-to-end | The §10 harness over `corpus/` and `corpus/reject/`, and over `corpus/gen/` (§11) |
| Native CLI, mutants | `tools/cli_check.py` (§10), `tools/mutate.py` (§11a) |
