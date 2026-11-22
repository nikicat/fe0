# 21. Keep frames in memory for now; reduce their cost in steps

- Date: 2026-11-12
- Status: accepted. Step 1 below is [0023](0023-frame-pointer-on-the-stack.md)

## Context
[0007](0007-codegen-from-ast.md) keeps every parameter, local and return address in a memory
frame. It expects output "larger and more expensive than the official compiler's". Two facts
bear on that.

**The gas cost.** `tools/gas_compare.py` (task Tsm5t2) sends each corpus program's call script
to Fe0's build and to Fe's builds on anvil. README.md, "Results", gives Fe0's gas over Fe's by
kind of program. Fe0 costs about the same as Fe on storage-bound programs, such as `amm.fe`
(a swap: 44,278 gas against 44,079 on Fe 26.7.0), and much more on arithmetic and calls.

In a function, a local costs about 12 gas to read (`DUPn PUSHn off ADD MLOAD`), against 3 for
a `DUP`. Storage costs thousands of gas per access in both builds, so it hides the difference.

**The recursion depth.** Each build runs out of EVM stack at its own depth
([0023](0023-frame-pointer-on-the-stack.md) gives depths), so near either limit, a call may
revert under one build and succeed under the other. That breaks the subset rule's promise of
the same behaviour.

## Decision
- **Keep memory frames for the submission.** The code generator stays as simple as
  [0007](0007-codegen-from-ast.md) made it, and the compiler stays within its contract-size
  budget. For the contracts that [0016](0016-steps-toward-real-contracts.md) aims at, which are
  storage-bound, the cost is a few percent.
- **Qualify the subset rule for depth.** SPEC.md states that Fe0 behaves the same as Fe below
  both builds' stack limits, given enough gas. A program that recurses near either limit is
  outside what the harness compares. The other choice, rejecting recursive cycles in the
  checker, is ruled out below.
- **Reduce the cost in steps, each measured** with `tools/gas_compare.py` for gas and
  Back's runtime size (`fe0-chain`, `-O s`) for the code generator's size:
  1. Keep the frame pointer on the stack, under the function's words
     ([0023](0023-frame-pointer-on-the-stack.md) has the design and the measured gain).
  2. Keep the parameters and locals of a function on the stack, when it calls nothing and has
     at most 16 live words.
  3. A peephole pass in the assembler. For example, when a store is followed by a load of the
     same slot, the pass keeps the word on the stack with a `DUP` and drops the load.

## Alternatives
- **Locals on the stack everywhere, as Fe does:** the stack-scheduling work that
  [0007](0007-codegen-from-ast.md) ruled out.
- **Reject recursive calls:** the subset rule would hold exactly. But Fe0 would refuse every
  recursive program, including the shallow ones that behave the same, to match a limit that
  comes from the EVM stack, not from the language.
- **An IR with optimization passes:** ruled out by [0007](0007-codegen-from-ast.md) for size
  and time, and still too large for the window.

## Consequences
- The submission states Fe0's gas over Fe's by kind of program (README.md, "Results").
- Recursion near either build's stack limit is a known difference, stated in SPEC.
