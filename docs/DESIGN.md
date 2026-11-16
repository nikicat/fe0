# Fe0 compiler design

How the compiler is built. [SPEC.md](SPEC.md) defines what Fe0 means, and [PLAN.md](PLAN.md)
covers scope and schedule. This document describes the compiler as it is meant to be; the
reasons for each choice are in [docs/adr/](adr/README.md).

Guiding rules:
- Prefer the simplest thing that is correct.
- The input programs are small (a few KB), so linear scans and fixed-size encodings are fine.
- Every shortcut is marked with a `ponytail:` comment in the code, naming its limit.

## 1. Repository layout (in the window)

```
fe.toml         a workspace whose members are the compiler's ingots. Without it, Fe's language
                server loads every .fe file outside an ingot as a standalone file and reports
                its errors. With it, the server analyses the member ingots only
fe0/            ingot: the compiler as a library; no I/O, target-agnostic
  src/lexer.fe  tokens
  src/ast.fe    arena AST
  src/parser.fe recursive descent
  src/check.fe  names, types, constants, effects
  src/codegen.fe AST → EVM ops with labels, laid out as initcode and runtime code
  src/asm.fe    opcodes, pushes and label resolution
  src/diag.fe   error codes and positions
  src/io.fe     the `Source` effect and its adapter, BytesReader (`text` and `bytes`)
  src/wire.fe   the words that carry one phase's output to the next phase's contract (§8)
  src/difftest.fe what each differential test calls: both builds, deploy, call, compare (§10)
fe0-cli/        ingot: native `main`, stdin → hex on stdout, errors on stderr (§9)
fe0-chain/      ingot: one contract per phase plus Compiler (on-chain split, §8)
  src/lib.fe    the contracts and their messages; the wire format is fe0/src/wire.fe
  Compiler.abi.json  Compiler's interface for callers; README.md explains it
corpus/         Fe0 programs (*.fe) + call scripts (*.calls); generated ones under corpus/gen/
corpus/reject/  programs that Fe0 must reject, each with the error it expects
out/            written by the tools, not committed
  difftest/     batch ingots of the differential tests, written by tools/embed.py
  gen/          batch ingots of the random programs, written by tools/gen.py
  cli-check/    batch ingots of tools/cli_check.py
  cli/          the CLI executable, built by tools/cli_check.py
  chain/        fe0-chain's contracts, built by tools/chain_check.py
tools/          embed.py, fegen.py (shared by the generators), gen.py (random programs),
                cli_check.py (the native CLI against the EVM, §10), chain_check.py (the
                compiler on chain against the CLI, §8), deploy.py (deploys the compiler on
                chain and runs its demo), compile_on_chain.py (compiles a program with the
                deployed compiler), corpus_scan.py, gen_codegen_tests.py and
                gen_check_tests.py (the unit-test generators), spikes.sh (the spike probes)
deployments/    the addresses of the deployed compiler, by chain id
docs/DEMO.md    the demo of the compiler on Arbitrum One
```

The `fe0` library is shared by every target. Only the edge ingots know where bytes come from.

## 2. Lexer

- **Input:** the lexer pulls bytes one at a time through `uses (input: mut Source)` and keeps one
  byte of lookahead. It appends each byte to the source buffer, a `Text`, as it reads it.
  `Source` is fe0's own effect, and [ADR 0010](adr/0010-source-effect.md) says why it is
  not std I/O.
- **Tokens** are spans of the source buffer, so the lexer never copies the text. `Token` is
  declared in `fe0/src/lexer.fe`.
- **Integer literals:** the lexer checks only their syntax. The parser computes each value once,
  with `Text.int_value`, when it stores it in the AST. It reports `L004` there if the value
  needs more than 256 bits, so the first error in source order wins.
- **Keywords:** the lexer packs the bytes of each identifier into one word (`Text.packed`). It
  looks that word up in tables of packed spellings in `fe0/src/lexer.fe`.
- **Newline tokens** are kept, except where the innermost open bracket is `(` (SPEC §3.4).
  `Lexer.open` tracks the open brackets. Where a newline is kept, the parser decides whether
  it ends a statement. Where it is dropped, the lexer checks that the line ends with `(`, `,`
  or a binary operator (`Tok.may_end_line_in_parens`), or that `)` comes next, and reports
  `L_LINE_BREAK` otherwise.
- **Doc comments** are `T_DOC` tokens, even inside `( )`. `Parser.skip_docs` skips them only
  where SPEC §1 allows them, so a doc comment anywhere else is a syntax error.
- **Positions:** line and column are computed only when an error is reported, by scanning the
  source buffer up to the error offset.

## 3. AST: an index-based arena

The AST lives in flat arrays and refers to nodes by index
([ADR 0005](adr/0005-arena-ast.md)). Index 0 means "none". A child list is a
length-prefixed run in one array. Ids, operators and written types are typed (`NodeId`,
`ListId`, `Sym`, `WordId`, `Tok`, `Ty`), so none of them travels as a bare integer.
`fe0/src/ast.fe` declares `Ast`, `Node` and the fields of each node kind.

- **Building lists:** one stack, `Parser.pending` in `fe0/src/parser.fe`, serves all lists, since
  inner lists close before outer ones.
- **Interning:** a linear scan over `syms`, in `Ast.intern`.
- **Check results go in side tables** (`types`, `res` and `slots` indexed by node, `places` by
  field and `events` by event, §5). The AST's nodes are never mutated after parsing. The
  checker only appends to `words`, as `Ast.words` says.

## 4. Parser

- Recursive descent, one function per grammar rule in SPEC §3.1.
- Binary expressions use precedence climbing with the SPEC §3.2 table.
- **No error recovery** ([ADR 0006](adr/0006-no-error-recovery.md)): the first error ends
  the parse. `parse()` reports it in `Ast.err` instead of returning a `Result`
  ([ADR 0011](adr/0011-error-field-not-result.md)).
- **Recursion is bounded:** nesting depth is capped at `MAX_DEPTH` in `fe0/src/parser.fe`
  ([ADR 0012](adr/0012-max-depth.md)).
- **Statement terminators** follow SPEC §3.4. Any other token after a statement or an
  item is `P_EXPECTED_END`.

## 5. Checker

`check(ast)` in `fe0/src/check.fe` returns a `CheckOutput`. Its program is a `Checked`, which
documents what each of its fields holds.

Constants are evaluated before any body, in source order (`Checker.program`).

- **Types:** the checker reuses `Ty` from `fe0/src/ast.fe` and adds types of its own. The
  `TY_` constants there document each one, and `Ty.fits` says which type fits which. Because
  `TY_NEVER` fits any type, `if c { return 1 } else { x }` has the type of `x`.
- **Scopes:** a stack of locals, innermost last (`Body.locals`). Lookup scans it from the
  top, then the contract fields, then the items. A block truncates the stack back to where it
  started. `Checker.declare` rejects a local or parameter named like a contract field (a
  storage field or an effect) or an item (SPEC §5.2).
- **Constants:** evaluated during checking with the same checked arithmetic as run time.
  Overflow gives `C034` and division by zero `C025`.
  - Only earlier constants may be referenced.
  - Both operands of `&&` and `||` are evaluated. `eval_binary` in `fe0/src/check.fe` says why.
- **Effects:** `init` and each arm get a `Grant` built from their `uses` (`Checker.grant`).
  `FieldSet` in `fe0/src/check.fe` bounds the number of contract fields.
  - A contract's effects are contract fields, as `NODE_FIELD` in `fe0/src/ast.fe` says. So the
    unused-entry warning and the name rules treat them as fields with no extra code.
- **Maps:** a map field has one of the map types, which `Ty::map` builds from the key and value
  types. A name that `Ty.is_value` rejects is not a value (`N003`) and is not assignable
  (`N014`). `m[k]` is an INDEX node, and `m[k] = v` is an ASSIGN whose place is that INDEX.
  `Checker.entry` checks the INDEX in both. Reading or writing an entry checks the map's grant,
  as for a field (below).
- **Storage:** `Checker.fields` gives each field a `StoragePlace`, its slot and its bytes in the
  slot (SPEC §6). `Ty.storage_bytes` gives an effect zero bytes and a map 32, so a map has a
  slot to itself (SPEC §6, "Maps"). Code generation writes a field that shares its slot by
  reading the slot, clearing the field's bytes and `OR`ing the new value in. A field alone in
  its slot is read and written whole, and so is a map entry.
  - A field read checks `Grant.read` (`E116`), and an assignment checks `Grant.write` (`E018`).
  - Free functions are pure (SPEC §5), so `fn_item` gives them an empty grant.
  - Duplicate entries are an error. An entry the body never reads or assigns is a warning,
    `E003`, collected in `CheckOutput.warns`.
- **Events** (SPEC §6, "Events"): `Checker.event_item` gives each field of an event its word of
  the log data (`Checked.log_word`). It records the event's `EventLog`: topic 0, which
  `Checker.topic0` builds from the source, and the number of data words (`Checked.topic0`,
  `Checked.data_words`). Code generation reads only these. The update to
  [ADR 0019](adr/0019-events.md#update-nov-12) says why it hashes with
  `std::evm::crypto::keccak256`.
- **Calls** (SPEC §6, "Calls"): a call does not name its effect, so the checker finds the
  contract's one `Call` effect by its type (`Checker.note_call_effect`), and
  `Checker.use_call_effect` checks the body's grant of it. The address is a NAME node, checked
  as any name. The values are checked as an emit's are (`Checker.labeled_args`). The call's
  VARIANT is its `res`, and code generation reads the selector, the field order and the return
  type from it, so a call adds no side table.
- **Selectors** (SPEC §6): `Checker.msg_item` checks the selectors of each msg (`T004`,
  `N016`), and `Checker.distinct_received_selectors` checks them across the msgs the contract
  receives (`N016`).
- **Return paths:** a body must have the type of its return type. A body that ends in `return`
  on every path has type `TY_NEVER`, so no separate "always returns" analysis is needed. A
  block with a final expression has that expression's type, even after `return` (SPEC §5).
- **Recursion:** the checker recurses over the AST as the parser does, so the parser's
  `MAX_DEPTH` bounds it too, as `check_tests::deep_nesting_and_long_chains` checks. An
  `else if` chain is checked in a loop.

## 6. Code generation

Opcodes are emitted straight from the AST, with no IR
([ADR 0007](adr/0007-codegen-from-ast.md)).

### 6.1 Memory layout

| Range | Use |
|---|---|
| `0x00–0x3f` | Scratch: return value, panic payload head, the key and slot that a map entry's slot is hashed from |
| `0x40` | **FP**, the current frame pointer |
| `0x60–0x7f` | Reserved (EVM convention, unused) |
| `0x80…` | Frames, growing upward. While `log.emit` runs, its data and topics are in the words past the current frame. While `a.call(…)` runs, its calldata is there |

**Frames.** Each function has a frame of `2 + params + locals` words at FP:
- `[FP+0]` saved FP of the caller;
- `[FP+32]` return address;
- `[FP+64…]` parameters, then locals.

Every local has a fixed slot assigned by the checker, with no slot reuse
(`ponytail: frame size = all locals; reuse slots if gas matters`). `init` and each arm run in
the first frame, at `0x80`, since nothing calls them (`Gen.begin`).

### 6.2 Calling convention

**Caller:**
1. Evaluate the arguments left to right onto the stack.
2. `newFP = FP + caller_frame_size`.
3. Store the arguments into `[newFP+64+32i]`, the return label into `[newFP+32]`, and FP into
   `[newFP+0]`.
4. Set `FP = newFP` and `JUMP` to the callee.

**Callee on return:** the result is on the stack (§6.3, "Leaving early"). The callee restores
`FP = [FP+0]` and jumps to the saved return address.

This supports recursion, and memory grows with call depth. Gas bounds both recursion depth and
memory cost.

The initcode and the runtime code each hold a copy of the functions they call, after their own
bodies (`Gen.functions` in `fe0/src/codegen.fe`).

### 6.3 Expressions

Each expression leaves exactly one word on the stack (unit-typed ones leave nothing).

| Construct | Emitted |
|---|---|
| Literal | `PUSHn` (the minimal n), `PUSH0` for 0 |
| Local | `MLOAD(FP + off)`: `PUSH1 0x40 MLOAD PUSHn off ADD MLOAD` |
| Field | `PUSHn slot SLOAD`, then `SHR` and `AND` only when it shares the slot (SPEC §6) |
| `a + b` | eval a, eval b, `DUP2 ADD`, `DUP1 SWAP2 GT` → `JUMPI panic_11` |
| `a - b` | eval a, eval b, `DUP2 DUP2 GT` → `JUMPI panic_11`, `SWAP1 SUB` |
| `a * b` | `MUL`, then if `a != 0 && r / a != b` → `panic_11` |
| `a / b`, `a % b` | `b == 0` → `panic_12`, then `DIV`/`MOD` |
| `<< >>` | `SHL`/`SHR`, which take the shift amount `b` on top. They never fail (SPEC §4) |
| `&& \|\|` | Short-circuit with `JUMPI` |
| Comparisons | `b` is on top, so `a < b` is `GT` and `a > b` is `LT`. `ISZERO` negates for `<= >= !=` |
| `!b` | `ISZERO`. `~a` is `NOT` |
| `assert!(c)` | `c ISZERO JUMPI panic_01` |
| `assert!(c, "m")` | `JUMPI` past an inline block that `MSTORE`s `Error(string)` and `REVERT`s |
| `ctx.caller()`, `ctx.address()`, `Address::zero()` | `CALLER`, `ADDRESS`, `PUSH0` |
| `m[k]` | eval k, `PUSH0 MSTORE`, `PUSHn slot PUSH1 0x20 MSTORE`, `PUSH1 0x40 PUSH0 KECCAK256 SLOAD` |
| `m[k] = v` | eval v, then k's slot as for `m[k]`, then `SSTORE`. Fe evaluates `v` first (SPEC §4) |
| `m[k] op= v` | eval v, k's slot, then `SWAP1 DUP2 SLOAD SWAP1`, the operator, `SWAP1 SSTORE` |
| `log.emit(E { … })` | eval each value as written, then `MSTORE` each past the frame at its field's word, `MLOAD` the indexed ones back as topics, then `PUSH topic0`, the data's size and offset, `LOGn` |
| `a.call(M::V { … })` | eval `a`, then each value as written. `MSTORE` each value past the frame at word 1 plus its field's index, and the selector at word 0, so that its 4 bytes end that word. `CALL` with `GAS`, no value, the calldata from byte 28 and no return buffer, then `ISZERO` → `JUMPI revert_returndata`. With a return type: fewer than 32 bytes of return data → `revert_empty`, then `RETURNDATACOPY` the first word to scratch, `MLOAD` it and check it as an arm checks an argument |

The table sketches each sequence. `Gen.apply` and its neighbours in `fe0/src/codegen.fe` emit the
exact ones. The differential tests of §13 check their results against Fe, not the instructions.

- **Stubs:** one shared block per panic code (`0x01`, `0x11`, `0x12`), one that reverts
  with empty data, and one that reverts with the return data of the call that failed. Each piece of code holds the ones it jumps to (`Stub` in
  `fe0/src/codegen.fe`). A panic stub stores `0x4e487b71 << 224` at 0 and the code at 4, then
  `REVERT(0, 0x24)`.
- **Leaving early:** a body can leave while it still has words on the stack, such as the `1`
  pending in `1 + { return 2 }`. A function pops the words under its result before it returns
  (`Gen.leave`). `break` and `continue` pop down to the depth at the start of the loop
  (`Gen.drop_to`). Arms end in `RETURN` or `STOP`, and `init` jumps to the code that returns the
  runtime code, so leftover words do not matter there.
- **Control flow:** `if`, `while`, `break` and `continue` lower to labels and `JUMPI`. The
  codegen keeps a loop-label stack for `break` and `continue`.

### 6.4 Dispatcher (runtime entry)

Mirrors the official compiler (SPEC §6):

```
CALLVALUE → JUMPI revert_empty         ; all arms are non-payable
CALLDATASIZE 4 LT → JUMPI revert_empty
0 CALLDATALOAD 224 SHR                  ; selector
for each arm: DUP1 PUSH4 sel EQ → JUMPI arm_k
revert_empty: 0 0 REVERT
```

Each arm then:
1. Checks `CALLDATASIZE >= 4 + 32n`.
2. Loads each argument word, checks `bool ≤ 1` and `Address >> 160 == 0`, and stores it into
   the arm's frame.
3. Runs the body.
4. `MSTORE(0, result)` then `RETURN(0, 32)`, or `STOP` for unit.

- A single up-front `CALLVALUE` check is safe because every failing path reverts with empty
  data, so the order of checks is unobservable.
- `ponytail:` the arms are a linear chain of `EQ`s. Use a binary search over sorted selectors,
  like the official compiler, only if gas matters.

### 6.5 Deployment layout

```
[ initcode ][ runtime ][ constructor args, appended by the deployer ]
```

The initcode:
1. Checks `CALLVALUE == 0`. The official initcode also rejects value, so the CREATE fails
   (`init_with_value` in `spike-conform/src/init_args.fe`).
2. Checks `CODESIZE >= init_len + rt_len + 32n`.
3. `CODECOPY`s the arguments into the `init` frame and validates them as in the dispatcher.
4. Runs the `init` body.
5. `CODECOPY`s the runtime to memory 0 and `RETURN`s it.

A contract without `init` skips steps 2–4, so extra bytes after the runtime are ignored.
`init_len` and `rt_len` are constants that the layout fills in (§7).

## 7. Assembler

- `Asm` in `fe0/src/asm.fe` holds one piece of code in a `MemVec<u8>`.
- **Jumps** always use `PUSH2 <label>` (see `MAX_CODE` in `fe0/src/asm.fe`). Each use is
  recorded as `(byte_offset, label)` in a fixup list. `generate` in `fe0/src/codegen.fe` reports
  code of 64 KB or more as `G002`.
- **Labels** are bound with `JUMPDEST` (`Asm.bind`), or without one (`Asm.mark`) when they are
  only pushed as a length.
- **Finish:** patch every fixup.
- **Layout:** `generate` assembles the runtime code first, so that the initcode can push its
  length. The initcode's own length is the label marked at its end.

There is a single pass with no relaxation, because the 2-byte targets keep offsets stable.

## 8. On-chain split (24 KB limit)

Each phase is its own contract, because lexer and parser together already exceed 24,576 bytes
([ADR 0014](adr/0014-contract-per-phase.md), with the measurements). Builds use `-O s`.

| Contract | Message | Does |
|---|---|---|
| `Lexer` | `lex(bytes src) -> uint256[]` | lex, then put the tokens |
| `Parser` | `parse(bytes src, uint256[] toks) -> uint256[]` | parse, then put the AST (`Ast.put`) |
| `Checker` | `check(bytes src, uint256[] ast) -> uint256[]` | check, then put the checked program (`Checked.put`) |
| `Back` | `generate(uint256[] ir) -> bytes` | take the checked program, generate and assemble, return the deploy code |
| `Compiler` | `compile(bytes src) -> bytes`, `deploy(bytes src, bytes args) -> address` | `STATICCALL` each phase in turn; `deploy` appends `args` and runs `create_raw` |

The contracts are in `fe0-chain/`. Compiler takes the four phase addresses in its constructor.
Callers use `fe0-chain/Compiler.abi.json`. `tools/chain_check.py` writes it and says why it
differs from the ABI that `fe build` writes.

- **Wire format:** each phase returns ABI `uint256[]`, in the format of `fe0/src/wire.fe`. The
  source does not cross. It is each phase's own `bytes` argument, so Back never sees it.
- **Errors:** see `CompileError` in `fe0-chain/src/lib.fe`. Warnings do not cross (§9).
- **Trust:** a phase contract trusts its input and decodes it without checks. Compiler, its
  intended caller, gives each phase the previous phase's output. A direct caller that sends
  malformed words gets a revert or a wrong result, and only for itself: the phases keep no
  state, so the call changes nothing on chain. Checks would cost bytes in Parser and Checker,
  which sit near the limit.
- **Measured on Fe 26.6.0 at `-O s` (Nov 16):**

  | Contract | Runtime bytes | Deploy gas |
  |---|---|---|
  | Lexer | 6,031 | 1.34M |
  | Parser | 22,694 | 4.95M |
  | Checker | 22,395 | 4.89M |
  | Back | 17,619 | 3.86M |
  | Compiler | 1,893 | 0.49M |

  - **Deploying all five costs 15.5M gas.**
  - **Compiling costs up to 29.7M gas, for `corpus/amm.fe`.**
    - That program is 8,141 bytes of source.
    - Lexing takes about 1,280 gas per byte of source.
      This figure was measured once, by hand.
      An `eth_estimateGas` of the Lexer's `lex(bytes)` on `corpus/amm.fe` gave the total.
      The gas of the same transaction to an account with no code was taken off it.
    - No tool measures the cost of the boundaries.
      We expect it to be small next to the phases themselves, but this is an estimate.
  - **`deploy` of `counter.fe` costs 2.2M gas.**
  - `tools/chain_check.py` measures the runtime bytes and the deploy gas of each contract.
    It also measures the largest compile gas and the deploy gas of `counter.fe`.
    It checks the limits.

## 8a. Measured limits of the host (official Fe on the EVM)

Measured Oct 28 on master `d217a51bf` (`spike-limits/`, 30M gas per call):

- **`MemVec` growth is linear:**
  - 237 gas per pushed byte at 1k, 4k and 16k items;
  - three interleaved vectors (bytes, 5-field nodes, `u32` lists) cost 851–902 gas per item.

  So the arena design is affordable: about 1M gas for the AST of a 2 KB program.
- **Recursion depth is bounded by the EVM stack, not by gas:** at most **1,019** nested calls
  for a one-argument function. Fe keeps return addresses on the 1,024-slot EVM stack, and
  functions with more live values get less depth.
  - **Consequence:** the parser caps its nesting depth and reports `P_TOO_DEEP` instead of
    overflowing the stack ([ADR 0012](adr/0012-max-depth.md), with the measurements).
  - This limits only the compiler running on chain. Code *generated by* Fe0 keeps its frames
    in memory (§6.1), so it has no such limit.
- **`fe test` does not enforce EIP-170:** 24,577 and 49,152-byte runtimes deploy fine.
  - The harness therefore asserts sizes itself: Fe0's own contracts (the phase contracts and
    Compiler) at most 24,576 bytes of runtime code, and Fe0's output for every corpus program
    likewise.
  - The initcode limit (EIP-3860) is not enforced either. 49,153 bytes of initcode deploy
    fine (measured Nov 6). The harness checks both limits on Fe0's builds (§10, item 6).
  - **A real node does enforce it.** Local `anvil` (Foundry 1.8.4, hardfork BPO1) deploys a
    24,576-byte runtime and rejects 24,577 bytes (status 0).
  - So the final gate is a real node: `tools/chain_check.py` (§8) deploys Fe0's contracts on
    `anvil` in CI and before any Arbitrum One deploy. A Fe-built `.bin` deploys and works
    there: the spec Counter returns `get() = 2` after two increments, and its on-chain runtime
    size equals `fe build`'s `.runtime.bin` (99 bytes).

## 9. Diagnostics

Every phase reports an error as a `Diag`. `fe0/src/diag.fe` declares it and defines how codes
are numbered and printed. The messages are a table in `fe0-cli/src/messages.fe`, because only
the CLI prints them, so the on-chain compiler does not pay for them in bytecode.

Inside the lexer, the parser and the checker, a function that can fail returns
`Result<Diag, T>`, or `Result<Diag, ()>` when it has no value. Callers pass the error on
with `?`. These functions use `Result` itself, not a result type of their own, because a `?`
after each call is the shortest way to stop at the first error. Only the phase entry points
differ: they report the error in a field instead
([ADR 0011](adr/0011-error-field-not-result.md)).

| Phase | Examples |
|---|---|
| Lexer | bad character, unterminated string, malformed integer |
| Parser | expected token, end of statement, chained comparison, literal over 256 bits (`L004`) |
| Names | unknown name, duplicate item, local shadows a field |
| Types | mismatch, missing return path |
| Effects | field not in `uses`, write without `mut`, unknown field, duplicate entry |
| Constants | overflow (`C034`), division by zero (`C025`) |
| Generation | no contract (`G001`), code too large (`G002`) |

The CLI prints `<stdin>:line:col: CODE message` on stderr and exits with 1. On chain, Compiler
reverts with `CompileError`, which holds the code and the byte offset (§8).

The checker also reports warnings, in `CheckOutput.warns`. They never stop the compile.
- The CLI prints each one on stderr as `<stdin>:line:col: warning: CODE message` and still
  writes its output.
- On chain, Checker puts only the checked program, so they do not cross. `compile` returns only
  the deploy code and `deploy` only an address, so nothing would read them.

## 10. Differential test harness

`tools/embed.py` runs the corpus. Its docstring gives the formats of call scripts and reject
headers. For each `corpus/X.fe` with its call script `X.calls`, it writes a module of a batch
ingot under `out/difftest/` that holds:

1. a copy of the program, compiled by the official compiler;
2. a runner function with the program as written in a string literal, and one `#[test]` that
   calls the runner. The runner calls `fe0/src/difftest.fe`, which:
   1. compiles the string with the `fe0` library *inside the test*, so on the EVM;
   2. copies the official build's initcode out of the test's own code, from
      `C::init_code_offset()` and `C::init_code_len()`;
   3. deploys both builds the same way, with `create_raw` and the arguments of the script's
      `init` line. Bad initcode gives address 0 rather than a revert
      (`spike-lexer/src/create_raw.fe`). Every other `deploy` line must create a contract from
      both builds or from neither;
   4. sends every call of the script, then the dispatcher probes of `fegen.DISPATCH`, to both
      contracts with `try_call_raw`;
   5. asserts that the success flag and the returndata bytes are equal, including revert
      payloads. Storage is compared through the calls that read it;
   6. asserts that a chain would accept Fe0's build. `fits_chain` checks the create input and
      the runtime code against the EIP-3860 and EIP-170 limits, which the test EVM does not
      enforce (§8a).

A failed test reverts with a typed error for each kind of failure, which says what failed and
where. The errors are the `#[error]` structs of `fe0/src/difftest.fe`, and `tools/fegen.py`
decodes them. Each error names itself by its selector. Both sides spell each error's name and
fields, and `fegen.check_errors` checks that they agree. `embed.py` turns each error into a
message that names the line of the call script, the dispatcher probe or Fe0's error.

The codegen tests (`fe0/src/codegen_tests.fe`) are differential tests of the same kind. They
live in the `fe0` ingot, so that `fe test` there runs them, and their generator shares
`tools/fegen.py` with `embed.py`.

Path dependencies between ingots work (`spike-deps/user`). Embedding sources as string
literals is fine too. The largest corpus program, `corpus/amm.fe`, is about 8 KB. A one-off probe, which is not
in the repository, passed a 32 KB `DynString` literal to a function. `fe test -O 0` built and
ran it in about 0.1 s.

Each batch ingot holds `BATCH` programs and depends on `fe0` by path. One `fe test --jobs 0`
run tests all the batches. [ADR 0003](adr/0003-own-corpus-and-generator.md#measurements) gives
the measurements behind this layout.

**On a node.** Inside `fe test`, every call comes from the test contract, and logs are not
visible. `tools/node_check.py` ([ADR 0016](adr/0016-steps-toward-real-contracts.md), step 0)
runs the same call scripts on a local anvil node instead (`tools/node.py`). It deploys Fe0's
build and Fe's build and sends each entry from the account its `from=N` names. The docstring of
`node_check.py` lists what the two builds must agree on. `tools/gas_compare.py` runs the same
way and reports each build's gas.

A call script may first deploy other programs for the program to call (SPEC §6, "Calls"), as
in `deploy token.fe as t0`, pass the address as `@t0` and call it, as in `@t0 Transfer @this 5`.
The docstring of `tools/embed.py` gives the format. Such a program runs only on a node, since
its test inside `fe test` could not deploy the other program. So does a program whose script
names a deployment such as `@this`, since that test could not resolve its address
(`fegen.Cases.node_only`). On the node, each build deploys its own build of each callee and
runs the whole script from the same snapshot of the node (`Node.session` in `tools/node.py`).
So the contracts of both builds get the same addresses, and a storage slot hashed from one is
the same in both.

**One test per batch.** The root module of each batch ingot holds one test that calls every
runner of the batch. Its name starts with `embed.BATCH_TEST`. The harness runs only these
tests. It runs the programs' own tests only in a batch whose test fails, to get each program's
error. The WORKAROUNDS.md entry on `fe test` compiling each EVM test alone says why.

**The reject tests run on the native backend**, for the same reason. A failed native test
prints its revert data as an EVM test does, so the harness reads each failing reject
program's error from that run.

**A program that the official compiler rejects would fail its whole batch.** So `embed.py`
first runs `fe check` on each program alone, about 0.2 s each and in parallel, and leaves out
and reports the ones it rejects.

**Negative tests:** `corpus/reject/*.fe` carry a header such as `// expect: E116 12:9`. Their
tests run Fe0 and check the error code and position. Separately, `embed.py` runs `fe check` on
each file and checks the result against the rule of SPEC.md §8.

**The native CLI.** `tools/cli_check.py` compares what the native CLI prints with what Fe0
does on the EVM, for every program of `corpus/`, `corpus/gen/` and `corpus/reject/`. Its
docstring lists what it checks.

## 11. Random program generator (`tools/gen.py`)

`tools/gen.py --seed S -n N` writes the programs of seeds S to S+N−1 to
`corpus/gen/s<seed>.fe` (git-ignored), each with its `.calls` script, and runs them through the
harness of §10 in `out/gen/`. CI runs the fixed seeds 1 to 25, so that a failure never depends
on chance. Other seeds run by hand. The module docstring of `tools/gen.py` describes the shape
of a program and what the generator guarantees.

The generator steers clear of a few shapes that Fe rejects or mishandles. Each one is marked
at the code in `gen.py` that avoids it, with its task id or its WORKAROUNDS.md entry.

**Throughput.** `tools/gen.py -n 25` takes about 15 s on 8 cores (Nov 8).
[ADR 0003](adr/0003-own-corpus-and-generator.md#measurements) gives the measurements.

Shrinking a failing program is a stretch goal. It would delete lines while the failure stays.

## 12. Hashing (`sol("…")` selectors, a stretch goal)

- `sol("f()")` needs keccak at Fe0's own run time. Fe0 hashes a signature with
  `std::evm::crypto::keccak256`, as `Checker.topic0` does. The update to
  [ADR 0019](adr/0019-events.md#update-nov-12) says why `core::keccak` cannot hash it.
- [ADR 0004](adr/0004-literal-selectors-first.md) says why selectors are literal first.
  [ADR 0015](adr/0015-move-to-26-6-0.md) says why hashing needs no `Hasher` effect.
- Remaining work: parse `sol("…")`, hash the signature, and take its first 4 bytes.

## 13. Testing per phase

| Phase | Unit tests (`fe test`) |
|---|---|
| Lexer | Token streams for each token class; error positions |
| Parser | Node-shape assertions for each grammar rule; a reject test for each `P` error |
| Checker | One accept and one reject per rule in SPEC §5–6, with error code and position |
| Codegen | Differential, as in §10. The tests are in `fe0/src/codegen_tests.fe`, generated by `tools/gen_codegen_tests.py` |
| Assembler | Pushes, and fixups of labels bound before and after their use |
| End-to-end | The §10 harness, run by `tools/embed.py` over `corpus/` and `corpus/reject/`, and by `tools/gen.py` over `corpus/gen/` (§11) |
| Native CLI | `tools/cli_check.py`, against Fe0 on the EVM (§10) |
