---
status: todo
deps: [Tjq40d]
tags: [fe0-chain, deploy]
---
# Deploy fe0-chain in a form Sourcify verifies

## Goal
Anyone can verify the source of fe0-chain's five contracts on Sourcify, without this
repository's git history. Done means a release of fe0-chain is deployed on Arbitrum One, and
Sourcify gives each of its five contracts a match.

## Decisions
- Verification is Sourcify's match, not a git tag (the user's decision, Nov 23).
- Sourcify rebuilds Fe source one way: it writes its own `fe.toml` with
  `name = "sourcify_verification"` and no dependencies, takes only `.fe` files under `src/`,
  and runs a bare `fe build`, which is `-O 1`
  (packages/compilers/src/lib/feCompiler.ts in argotorg/sourcify). The ingot's name changes
  the bytecode, so a deployment must be built exactly that way.

## Measured
At `-O 1` every contract fits EIP-170 (runtime bytes, `-O 1` against the deployed `-O s`):
Lexer 5,857 / 5,751, Parser 18,175 / 17,358, Checker 20,405 / 20,101, Back 17,728 / 17,296,
Compiler 1,731 / 1,706.

## Open
- fe0-chain depends on the `fe0` ingot, which Sourcify cannot take. Either fe0's sources go
  under fe0-chain's `src/` as a module, or Sourcify's Fe input learns dependencies (the
  upstream request, https://github.com/argotorg/sourcify/issues/3084). fe0's sources refer
  to their own modules through `ingot::` 43 times, so moving them under another ingot
  changes those paths.
- A new release has new addresses. The playground, docs/DEMO.md and the registry's demo then
  use the new Compiler.

## Next
Wait for the answer to https://github.com/argotorg/sourcify/issues/3084. If dependencies are
not coming soon, try building fe0-chain as one ingot and measure the sizes again.
