# 23. Keep a function's frame pointer on the stack

- Date: 2026-11-22
- Status: accepted; step 1 of [0021](0021-frames-gas-and-depth.md); amends the consequences of
  [0007](0007-codegen-from-ast.md)

## Context
Fe0 keeps every parameter and local in a memory frame ([0007](0007-codegen-from-ast.md)).
Code reads a local at FP plus its offset, so each read starts by pushing FP. With FP only in
memory at `0x40`, that push is `PUSH1 0x40 MLOAD`, which costs 6 gas. A `DUPn` costs 3.

The code generator counts the words that a body has on the stack (`Body.depth` in
`fe0/src/codegen.fe`), because code that leaves early must pop them.

## Decision
- **A function keeps its FP on the stack, under its words.** The caller pushes the callee's FP
  before it jumps, and the callee pops it when it returns. With `Body.depth`
  words above FP, code reads FP with `DUP(depth + 1)`.
- **A copy of FP is kept at `0x40`.** Every call and return writes it. `DUP16` reaches no
  deeper than 16 words, so when 16 or more words sit above FP, the code loads the copy.
- **`init` and the arms use constants.** They run in the first frame, at `0x80`, so a read is
  `PUSHn addr MLOAD`. They write the copy at `0x40` only when they call a function.

DESIGN.md §6.1 and §6.2 give the layout and the calling convention.

## Measurements (Fe 26.7.0)
- **Gas** (`tools/gas_compare.py`, the whole corpus): Fe0's total goes from 7,689,280 to
  7,303,943 gas, which is 5.0% less. Its ratio to Fe at `-O 1` goes from 1.51 to 1.43, and to
  `-O s` from 1.48 to 1.41.
  - Storage-bound programs, such as `tokens`, `vault` and `amm`, save 0.2% to 1.0%.
  - Arithmetic, loops and calls save 6% to 21%: `isqrt` 9.2%, `fib` 9.4%, `ackermann` 8.2%,
    `arith` 15.0%, `many_params` 20.5%.
- **Size:** Back's runtime code (`fe0-chain`, `-O s`) grows from 17,216 to 17,296 bytes, 80
  bytes more. It stays 7,280 bytes under EIP-170's limit of 24,576.
- **Recursion depth**, on anvil with 30M gas per call. In the second function, each call
  keeps `n` pending as well, which halves the depth:

  | Function | Fe0 | Fe `-O 1` |
  |---|---|---|
  | `down(n) = if n == 0 { 0 } else { down(n - 1) }` | 1,019 | 1,019 |
  | `sum(n) = if n == 0 { 0 } else { n + sum(n - 1) }` | 509 | 509 |

  Both builds keep about one word per pending call for the first function, and two for the
  second. But they keep different words on the stack, so other functions may reach different
  depths.
- **Tests:** `tools/node_check.py` finds no difference between Fe0's and Fe's builds of the 87
  corpus programs.

## Alternatives
- **FP only at `0x40`:** gas alone bounds recursion, but every read of FP costs 6 gas instead
  of 3.
- **No copy at `0x40`:** a call and its return would save three stores and a load, and each
  frame would lose its saved-FP word, which only restores the copy. But code with 16 or more
  words above FP would then need another way to reach FP, such as spilling words to memory,
  which the code generator does not have.

## Consequences
- Each pending call keeps its FP and the words it has pushed on the 1,024-slot stack, so the
  stack bounds Fe0's recursion, as it bounds Fe's. SPEC.md's subset rule leaves out a call
  near either build's limit.
- `Body.depth` must count every word above FP wherever code reads FP, since a wrong count
  copies the wrong word.
- Step 2 and step 3 of [0021](0021-frames-gas-and-depth.md) build on this layout.
