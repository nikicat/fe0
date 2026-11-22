---
status: doing
tags: [codegen, gas]
---
# Cheaper frames, in measured steps

## Goal
ADR 0021's steps. Each one is measured with `tools/gas_compare.py` for gas and Back's runtime
size (`fe0-chain`, `-O s`) for the code generator's size:
1. the frame pointer on the stack instead of at `0x40`, with a fallback past `DUP16`;
2. stack-only frames for leaf functions with at most 16 live words;
3. a peephole pass in the assembler.
Done means each step is either in, with its gain recorded in an ADR, or dropped with its
measured reason.

## State
- Step 1 is in, as ADR 0023: 5.0% less gas over the corpus (Fe0 ÷ Fe `-O 1` from 1.51 to
  1.43), and Back 80 bytes larger. The full check passes. Not committed yet.
- With step 1, the EVM stack bounds Fe0's recursion. ADR 0023 has the measured depths, and
  SPEC.md's subset rule leaves out a call near either build's stack limit.

## Next
- Step 2, after the code freeze of Nov 23 (T0010): leaf functions with at most 16 live words
  keep parameters and locals on the stack.
