---
status: todo
tags: [playground, unsmell]
---
# Receivers for chain access

## Goal
The playground's chain/ layer reads and writes the chain through free functions that each take
a `Deployed`, the type in `src/domain/config.ts` for one chain with its Compiler and registry
contracts. Those functions are viemChain, publicClient and txUrl in `chain/chains.ts`, and
walletOn, callTx and transact in `chain/transact.ts`. The TypeScript classes `Registry` and
`Compiler` in chain/ keep a `Deployed` only to pass it to those functions. The user wants such
functions to be methods of one class that owns the value.

Done means: one class in chain/, built once per `Deployed` (for example `ChainAccess`), with the
public client, the transaction link, an eth_call and a wallet transaction as its methods;
`Registry` and `Compiler` take it instead of a `Deployed`; ADR 0032 "Deployment" says what
chain/ takes. The hooks of state/ keep reading the deployment from the React context.

The unsmell run of 2026-11-24 found this in code it did not change (findings b3-22 and
cross-16 in `.git/unsmell/20261124-184332/findings/`).

## Next
Write `ChainAccess` in chain/, then move Registry and Compiler onto it.
