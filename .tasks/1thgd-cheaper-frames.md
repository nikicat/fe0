---
status: todo
tags: [codegen, gas]
---
# Cheaper frames, in measured steps

## Goal
ADR 0021, after the submission. Each step measured with `tools/gas_compare.py` for gas and
`spike-sizes` for the code generation contract's size:
1. the frame pointer on the stack instead of at `0x40`, with a fallback past `DUP16`;
2. stack-only frames for leaf functions with at most 16 live words;
3. a peephole pass in the assembler.
Done means each step is either in, with its gain recorded in ADR 0021's successor, or dropped
with its measured reason.
