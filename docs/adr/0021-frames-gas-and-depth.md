# 21. Keep frames in memory for now; reduce their cost in steps

- Date: 2026-11-12
- Status: accepted; amends the consequences of [0007](0007-codegen-from-ast.md)

## Context
[0007](0007-codegen-from-ast.md) keeps every parameter, local and return address in a memory
frame, with the frame pointer at `0x40`. It expected output "larger and more expensive than the
official compiler's" and counted unlimited recursion as a gain. Two things were not known then.

**The gas cost.** `tools/gas_compare.py` measured it on Nov 12 (task Tsm5t2). It sends each
corpus program's call script to Fe0's build and to Fe's builds on anvil. Fe0's gas over Fe's:

| Kind of program | Fe0 ÷ Fe (`-O 1`) |
|---|---|
| storage-bound, such as `tokens.fe`, `vault.fe`, `escrow.fe` | 1.00 to 1.08 (`tokens` 1.01) |
| `amm.fe`, a Uniswap v2–style pair without the tokens | 1.07 (a swap: 12,450 against 11,500) |
| arithmetic and loops, such as `isqrt`, `power`, `primes` | 2.0 to 3.7 |
| calls, such as `fib`, `ackermann`, `many_params` | 2.0 to 3.1 |
| the whole corpus | 1.81 |

A local costs about 15 gas to read (`PUSH1 0x40 MLOAD PUSHn off ADD MLOAD`), against 3 for a
`DUP`. Storage costs thousands of gas per access in both builds, so it hides the difference.

**The recursion depth.** Fe keeps return addresses on the EVM stack, whose 1,024 slots run out
at a recursion depth of about 1,010 for a one-argument function. Fe0 has no such limit. So a
call that recurses deeper reverts under Fe and succeeds under Fe0 (task T0gp3v). That breaks
the subset rule's promise of the same behaviour.

## Decision
- **Keep memory frames for the submission.** The code generator stays as simple as
  [0007](0007-codegen-from-ast.md) made it, and the compiler stays within its contract-size
  budget. For the contracts that [0016](0016-steps-toward-real-contracts.md) aims at, which are
  storage-bound, the cost is a few percent.
- **Qualify the subset rule for depth.** SPEC.md states that Fe0 behaves the same as Fe below
  Fe's stack limit, given enough gas. A program that recurses past Fe's limit is outside what
  the harness compares. The other choice, rejecting recursive cycles in the checker, is
  ruled out below.
- **Reduce the cost in steps after the submission, each measured** with `tools/gas_compare.py`
  for gas and `spike-sizes` for the code generator's size:
  1. Keep the frame pointer on the stack, under the function's words, instead of at `0x40`.
     A local read becomes `DUPn PUSHn off ADD MLOAD`, which saves about 6 of its 15 gas.
     `DUP16` is the deepest reach, so where more than 15 words sit above the frame pointer,
     the code falls back to a copy at `0x40`.
  2. Keep the parameters and locals of a function that calls nothing and has at most 16 live
     words on the stack.
  3. A peephole pass in the assembler, such as a store followed by a load of the same slot.

## Alternatives
- **Locals on the stack everywhere, as Fe does:** the stack-scheduling work that
  [0007](0007-codegen-from-ast.md) ruled out, and Fe's recursion limit with it.
- **Reject recursive calls:** the subset rule would hold exactly. But Fe0 would refuse every
  recursive program, including the shallow ones that behave the same, to match a limit that
  comes from the size of Fe's stack, not from the language.
- **An IR with optimization passes:** ruled out by [0007](0007-codegen-from-ast.md) for size
  and time, and still too large for the window.

## Consequences
- The submission states the gas ratios above, by kind of program.
- [0007](0007-codegen-from-ast.md)'s consequence "generated code may recurse as deep as gas
  allows" is no longer a gain under the subset rule. It is a known difference, stated in SPEC.
- Step 1 changes how every local is read, so it needs the whole differential suite and a new
  size measurement of the code generation contract.
