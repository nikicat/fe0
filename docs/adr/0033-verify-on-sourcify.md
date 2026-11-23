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
ingot named `sourcify_verification`, with no dependencies, at `-O 1`. After deploying it,
`tools/deploy_registry.py` submits its source to Sourcify's APIv2 and records the match in
`deployments/registry/<chain id>.json`. It errors when Sourcify finds no match or does not
answer, and then records nothing. A rerun finds the contract deployed and submits it again.

Both registries are built and verified this way. fe0-chain is not yet: it depends on the
`fe0` ingot and is deployed at `-O s`.

## Alternatives
- **A git tag for each release:** it needs the repository to stay available, and nothing
  outside the repository checks it.
- **Sourcify learns the ingot's name, the optimization level and dependencies:** our builds
  could stay at `-O s` under their own names. This needs a change in Sourcify, which
  [argotorg/sourcify#3084](https://github.com/argotorg/sourcify/issues/3084) asks for.

## Consequences
- The registries are built at `-O 1`, so their runtime code is larger than at `-O s`. On
  2026-11-23, with Fe 26.7.0, Registry's was 3,030 bytes against 2,932, and CompilerRegistry's
  was 1,811 against 1,793.
- fe0-chain's deployed contracts cannot be verified on Sourcify. Making them verifiable needs
  a release built as Sourcify rebuilds it, or the change in Sourcify. A new build has new
  addresses, since a CreateX address depends on the code (ADR 0028).
- Deploying the registry needs Sourcify's API to answer.
