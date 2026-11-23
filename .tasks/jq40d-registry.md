---
status: doing
tags: [registry, playground]
---
# The registry of deployed programs

## Goal
Build the registries of ADR 0031 and ADR 0034: Registry, which compiles a Fe0 program through
a listed Compiler, creates it through CreateX and records it with its source and deployers, and
CompilerRegistry, the list of Compilers that an admin keeps. Done means:
- both are checked on a local anvil node;
- both are deployed on Arbitrum One through CreateX, with browser-web3-signer, and Sourcify
  matches them (ADR 0033);
- the playground deploys through Registry, lists its contracts and opens each one with its
  source, constructor arguments and compiler.

## Decisions
- When the init code reverts, `deploy` errors with CreateX's `FailedContractCreation`, and a
  client runs the init code by `eth_call` for the reason (ADR 0031, "Deploying").
- `deploy` accepts only compilers that CompilerRegistry lists. Its admin is the deploying
  account, and the role moves in two steps, so it can later move to a trustless contract
  (ADR 0034).
- The tools build registry/ as Sourcify rebuilds it (ADR 0033).
  `deployments/registry/<chain id>.json` records the version, the admin, the addresses and the
  matches.

## State
Both registries are deployed on Arbitrum One and Sourcify matches both
(`deployments/registry/42161.json`). CompilerRegistry lists the Compiler of fe0-chain 0.1.4,
and `corpus/counter.fe` is deployed through Registry. `tools/registry_check.py` runs in CI's
"on chain" job.

## Next
Build the playground's registry views (ADR 0032): make `tools/playground.py` read
`deployments/registry/<chain id>.json`, make the Deploy form send `deploy` to Registry, and add
a list page of its contracts and a page that opens each one with its source, constructor
arguments and compiler.

## Upstream
Asked Sourcify to accept the ingot's name, the `-O` level and dependencies in its Fe input:
https://github.com/argotorg/sourcify/issues/3084.
