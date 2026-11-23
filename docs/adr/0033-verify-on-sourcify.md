# 33. Verify deployed contracts on Sourcify

- Date: 2026-11-23
- Status: accepted

## Context
fe0-chain is deployed on Arbitrum One, and `tools/deploy_registry.py` deploys the registry and
the compiler registry (ADR 0031, ADR 0034) there. A user of a deployed contract needs to know
which source it was built from. A git tag in this repository is weak evidence: it holds only
while the repository and the tag exist, and a reader has to trust that the tagged commit was the
one deployed. Etherscan, and so Arbiscan, verifies only Solidity and Vyper.
[Sourcify](https://sourcify.dev) verifies Fe. It rebuilds the source and compares the bytecode
with the chain's, and anyone can read the result.

Sourcify builds Fe source one way (`packages/compilers/src/lib/feCompiler.ts` in
argotorg/sourcify):
- it writes its own `fe.toml`, which names the ingot `sourcify_verification` and has no
  dependencies;
- it takes only `.fe` files under `src/`;
- it runs `fe build` with no options, which optimizes at `-O 1`.

The ingot's name changes the bytecode. On 2026-11-23, with Fe 26.7.0, the registry's source
was built at `-O s` once in an ingot named `fe0_registry` and once named
`sourcify_verification`. Registry's 2,932 runtime bytes differed in 30, and CompilerRegistry's
1,793 differed in 49.

## Decision
A contract counts as verified when Sourcify matches it, not when a git tag names its commit.

The tools build each contract that Sourcify should verify the way Sourcify rebuilds it: in an
ingot named `sourcify_verification`, with no dependencies, at `-O 1`. After deploying it, the
deploy tool submits its source to Sourcify's APIv2 and records the match with the deployment:
`tools/deploy.py` in `deployments/<chain id>.json`, and `tools/deploy_registry.py` in
`deployments/registry/<chain id>.json`. The tool errors when Sourcify finds no match or does
not answer, and then records nothing. A rerun finds the contract already deployed (ADR 0028)
and submits it again. When Sourcify verified it before, the tool records the match that
Sourcify recorded.

fe0-chain depends on the `fe0` ingot, which Sourcify cannot take. So the tools build one ingot
from fe0-chain's source and the modules of fe0 that it uses, with fe0-chain's `fe0::` paths
written as `ingot::` (`chain_sources` in `tools/chain_check.py`).

Compiler keeps the phases' addresses in a `mut` field, in storage, so that Sourcify matches
its runtime code too.

## Alternatives
- **A git tag for each release:** it needs the repository to stay available, and nothing
  outside the repository checks it.
- **Move fe0-chain's contracts into the `fe0` ingot:** Sourcify would show the repository's
  files unchanged. But the compiler library would then hold its on-chain deployment, and
  fe0's tests would be part of the verified source.
- **The phases' addresses in a field without `mut`:** Fe appends such a field to the runtime
  code and does not say where, so Sourcify would match only Compiler's creation code
  ([argotorg/fe#2077](https://github.com/argotorg/fe/issues/2077)).
- **Sourcify learns the ingot's name, the optimization level and dependencies:** our builds
  could stay at `-O s` under their own names, and fe0-chain could keep its dependency. This
  needs a change in Sourcify, which
  [argotorg/sourcify#3084](https://github.com/argotorg/sourcify/issues/3084) asks for.

## Consequences
- The registries are built at `-O 1`, so their runtime code is larger than at `-O s`. On
  2026-11-23, with Fe 26.7.0, Registry's was 3,030 bytes against 2,932, and CompilerRegistry's
  was 1,811 against 1,793.
- fe0-chain is built at `-O 1` too. On 2026-11-23, with Fe 26.7.0, its largest contract,
  Checker, had 20,405 runtime bytes, against 20,101 at `-O s`.
- Sourcify shows fe0-chain's source as the one ingot that the tools build, not as the
  repository's two ingots.
- Reading the phases' addresses from storage adds about 8,000 gas to a compile, against a
  field without `mut`.
- Deploying fe0-chain or the registry needs Sourcify's API to answer.
