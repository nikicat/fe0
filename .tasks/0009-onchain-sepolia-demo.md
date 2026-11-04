---
status: todo
deps: [T0003, T0005]
due: 2026-11-21
tags: [onchain]
---
# On-chain compiler, Sepolia deployment and demo

## Goal
The phase contracts and Compiler (DESIGN.md §8) that compile source sent in calldata and deploy
the result with `create_raw`. Deploy to Sepolia and script the demo: compile, deploy, call.

## Decisions
- One contract per phase (docs/adr/0014-contract-per-phase.md). The `Parser` contract needs a
  parse entry point that takes a `Lexed`, because `parse()` runs the lexer itself today.

## Next
Check the Foundry keystore `test` address and get Sepolia ETH from a faucet (needs the user).
Verify sizes on anvil first.
