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
`registry/src/` holds both contracts, in `compilers.fe` and `registry.fe`.
`tools/registry_check.py` passes on anvil and runs in CI's "registry" group, and
`tools/deploy_registry.py --rehearse` passes. `tools/sourcify.py` has not run against Sourcify
yet. The /unsmell run `.git/unsmell/20261123-142740` has findings that are not triaged; the
contracts and the tools were rewritten after its surveys. Nothing is committed.

## Next
Re-survey the rewritten files and review the /unsmell changes. Commit, deploy with
`uv run --project tools tools/deploy_registry.py`, and check that Sourcify matches. Then the
playground: `tools/playground.py` reads `deployments/registry/<chain id>.json`, the Deploy
form sends `deploy` to Registry, and a list page shows its contracts.

## Upstream
Asked Sourcify to accept the ingot's name, the `-O` level and dependencies in its Fe input:
https://github.com/argotorg/sourcify/issues/3084.
