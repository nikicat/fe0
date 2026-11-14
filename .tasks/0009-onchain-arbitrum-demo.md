---
status: doing
deps: [T0003, T0005, T324k1]
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
  newer than Arbitrum supports. Check this again on Fe 26.6.0 (T324k1).
- Deploy close to submission: the deployment is public, and PLAN.md risk 5 keeps the
  project private until Nov 24.
- Sign the deployments with `browser-web3-signer` (installed in `~/.local/bin`), so that
  no private key is in the repo or the shell. A contract is deployed with
  `browser-web3-signer evm send-transaction --chain <arbitrum> --data 0x<initcode>`, with no
  `--to`, and the user approves each one in their browser wallet.

## State
- The on-chain compiler is built, checked on anvil and committed (0096f38).
  - `fe0-chain/` holds Lexer, Parser, Checker, Back and Compiler.
  - The wire format is `fe0/src/wire.fe`.
  - Every contract fits EIP-170. Parser is the largest, at 22,072 runtime bytes.
- `tools/chain_check.py` deploys all five on anvil (Cancun). Then it checks three things:
  - all 50 corpus programs compile by `eth_call` to the CLI's exact bytes;
  - all 129 reject programs revert with their header's `CompileError`;
  - `deploy(bytes,bytes)` of `counter.fe` works.
- CI runs `tools/chain_check.py`.
- The gas numbers are in DESIGN.md §8:
  - deploying all five costs 15.4M;
  - compiling costs up to 14.8M, for `amm.fe`;
  - deploying `counter.fe` through Compiler costs 2.4M.
- `browser-web3-signer` 0.12.1 is installed with `cargo install --locked browser-web3-signer`.
  It lands in `~/.local/bin`. After a container rebuild, run that again.
- **Deployed to Arbitrum One on Nov 14** with `tools/deploy.py`. The addresses are in
  `deployments/42161.json`:
  - Compiler is at `0xc3166Af5e42019C1f986b2e1f4958D69C377fe79`.
  - The demo compiled `counter.fe` by `eth_call` (268 bytes of deploy code).
  - It then deployed `counter.fe` through Compiler at `0x58307ED5Db3E1F9EdCe546258Cbf2d23fBA89F57`
    (2,415,927 gas), and `Get` returns 2.
- Deploy gas on Arbitrum: Lexer 1.74M, Parser 4.88M, Checker 4.75M, Back 3.79M, Compiler 0.50M.

## Next
1. Script the public demo for the submission (T0010): the commands and what each shows.
