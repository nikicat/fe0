---
status: todo
deps: [T0003, T0005]
due: 2026-11-21
tags: [onchain]
---
# On-chain compiler, Arbitrum One deployment and demo

## Goal
The phase contracts and Compiler (DESIGN.md §8) that compile source sent in calldata and deploy
the result with `create_raw`. Deploy to Arbitrum One and script the demo: compile, deploy, call.

## Decisions
- One contract per phase (docs/adr/0014-contract-per-phase.md). The `Parser` contract needs a
  parse entry point that takes a `Lexed`, because `parse()` runs the lexer itself today.
- Compile with a free read-only call (`eth_call`), and send a transaction only to deploy the
  output. A compile costs 3.4–5.6M gas for a 1.1–1.7 KB corpus program (measured Nov 7 with
  `fe test -O s`), so a transaction would pay for nothing the demo needs.
- Deploy to Arbitrum One, not Sepolia: no faucet, and the deployment is cheap. The whole
  compiler as one probe (56,710 runtime bytes) took 12.31M gas to deploy on anvil, about
  217 gas per byte, so five phase contracts of 60–70 KB should take 13–16M gas, about
  0.0003 ETH at Arbitrum's 0.02 gwei floor plus the L1 data fee. The probe deploys on a
  Cancun-only anvil and compiles there by `eth_call`, so Fe 26.5.1's output needs no opcode
  newer than Arbitrum supports.
- Deploy close to submission: the deployment is public, and PLAN.md risk 5 keeps the
  project private until Nov 24.
- Sign the deployments with `browser-web3-signer` (installed in `~/.local/bin`), so that
  no private key is in the repo or the shell. A contract is deployed with
  `browser-web3-signer evm send-transaction --chain <arbitrum> --data 0x<initcode>`, with no
  `--to`, and the user approves each one in their browser wallet.

## Next
Build the phase contracts and check each one's size and deploy gas on anvil with
`--hardfork cancun`. Then deploy with `browser-web3-signer` from a wallet that holds about 0.001
ETH on Arbitrum One (needs the user).
