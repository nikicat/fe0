---
status: todo
deps: [T0002]
due: 2026-11-05
tags: [onchain]
---
# Measure the bytecode size of each compiler phase

## Goal
Decide how to split the on-chain compiler under the 24 KB limit (DESIGN.md §8). The lexer alone
is 3.1 KB. `fe test` does not enforce EIP-170, so measure explicitly and confirm on anvil.

## Next
Wrap lexer+parser in a probe contract and measure `.runtime.bin`. Fe master has
`fe build --emit sizes` (PR #1878), but it is not in 26.5.1.
