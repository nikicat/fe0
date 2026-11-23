---
status: doing
deps: [T0006, T0009]
due: 2026-11-24
tags: [contest]
---
# Submission

## Goal
Submit by Nov 24, 23:59 UTC. Registered as project **FE-001** (confirmed by email; it was in
spam). The prefilled submission link with the private submission code is in
`docs/registration-confirmation.txt`, which is git-ignored and must never be committed, since
the repo is public. Resubmitting before the deadline is allowed; the latest valid one counts.


## Decisions
- The submission includes steps 0 to 4 of ADR 0016, which are done. Step 5 (Tbzc0q) is
  named as the next step in the README's limitations. It also states the gas ratios of
  ADR 0021 by kind of program.
- Sourcify's match, not a git tag, shows which source a deployed contract came from
  (ADR 0033). Each release is deployed by `tools/deploy.py` and verified on Sourcify.

## State
- Arbitrum One runs fe0-chain 0.1.4. `deployments/42161.json` and docs/DEMO.md hold its
  addresses, and Sourcify matches the runtime code of all five contracts. CompilerRegistry
  lists Compiler 0.1.4 and no other.
- The repo is public, and Pages publishes the playground.
- README.md is written and reviewed. Its gas table and ADR 0021's were measured on Fe 26.7.0:
  over the whole corpus, Fe0's gas is 1.43 times that of Fe's build at `-O 1`.

## Next
- Commit and push the 0.1.4 release with its docs, wait for CI, and submit the new HEAD's
  SHA (Fe version `fe 26.7.0`) through the link in `docs/registration-confirmation.txt`.
- Try the playground in a browser against Compiler 0.1.4.
