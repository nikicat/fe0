# 28. Deploy the five contracts in one transaction through Multicall3 and CreateX

- Date: 2026-11-22
- Status: accepted

## Context
The on-chain compiler is five contracts: Lexer, Parser, Checker, Back and Compiler
(DESIGN.md §8). Compiler takes the four phase addresses in its constructor. `tools/deploy.py`
deploys them, and the user signs its transactions in a browser wallet through
`browser-web3-signer`, so no private key is in the repo or the shell. Multicall3 and CreateX
are widely used contracts, each at the same address on every chain that has it.
`deploy.py --rehearse` runs the same deployment on a local anvil node.

## Decision
`tools/deploy.py` deploys all five contracts in one transaction. The transaction calls
Multicall3's `aggregate3`, which calls CreateX's `deployCreate2` once per contract with a zero
salt.
- Multicall3 reverts when any call fails, so either all five contracts are created or none is.
- CreateX mixes neither the sender nor the chain id into a zero salt, so each address depends
  only on the contract's deploy code and constructor arguments. The addresses are known before
  the transaction, so Compiler's constructor gets the four phase addresses in the same
  transaction.
- Anyone can create the same contracts at those addresses first, but the code there is then
  the same, and the transaction leaves out each contract that already has code.
- The transaction is an ordinary one, so `browser-web3-signer` sends it as it is, and the
  rehearsal on anvil runs the same path.

## Alternatives
- **Separate transactions:** they are not atomic. A run that stops part way leaves contracts
  that no Compiler uses, and the next run must find and skip them.
- **An EIP-5792 wallet batch:** it can be atomic, but `browser-web3-signer` has no
  `wallet_sendCalls`, and no test shows whether a wallet runs a batch of contract creations.

## Consequences
- The chain must have Multicall3 and CreateX. `deploy.py` checks that before it sends, and
  `--rehearse` copies their code to anvil.
- A deployment's file in `deployments/` never records a partial deployment.
- A run after a full deployment sends only the demo's transaction (docs/DEMO.md §4).
