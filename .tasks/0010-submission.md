---
status: todo
deps: [T0006, T0009]
due: 2026-11-24
tags: [contest]
---
# Submission

## Goal
Submit by Nov 24, 23:59 UTC. Registered as project **FE-001** (confirmed by email; it was in
spam). The prefilled submission link with the private submission code is in
`docs/registration-confirmation.txt`, which is git-ignored and must never be committed, since
the repo goes public. Resubmitting before the deadline is allowed; the latest valid one counts.


## Decisions
- The submission includes steps 0 to 4 of ADR 0016, which are done. Step 5 (Tbzc0q) is
  named as the next step in the README's limitations. It also states the gas ratios of
  ADR 0021 by kind of program.
- The deployed contracts must be built from a release (fe0-chain/README.md, "Releases"), so
  the on-chain compiler is redeployed to Arbitrum One once, after the last code change. Code
  changes stop at the freeze on Nov 23. The release tag goes on that code, and the contracts
  are deployed from the tag. The commit after it changes only docs/DEMO.md and
  `deployments/42161.json`. A fix after the freeze needs a new release and a new deploy.

## State
- The compiler was redeployed to Arbitrum One on Nov 20 from eefab6f's code. DEMO.md and
  `deployments/42161.json` have the new addresses.
- README.md is written and reviewed. Its gas table and ADR 0021's were remeasured on
  Fe 26.7.0 (whole corpus 1.51).
- The starter's SUBMISSION.md is gone, but the registration email lists what a submission must
  include: a public GitHub repository, the exact commit, an OSI license, the Fe version, tests,
  build instructions, a README, a demo and disclosures. The README covers all of them but the
  commit, which goes in the form.

## Next
- Until the freeze: land fixes as usual. DEMO.md's `version()` call fails until the redeploy,
  because the deployed Compiler predates `version()`.
- Nov 23, the freeze: commit the last fixes, tag `v0.1.0` (fe0-chain/README.md, "Releases"),
  remove `deployments/42161.json` (deploy.py refuses a file from another release), run
  `tools/deploy.py`, then update the addresses in docs/DEMO.md and commit them with the new
  `deployments/42161.json`.
- Nov 24: push the branch and the tag, make the repo public (Apache-2.0 LICENSE is in place),
  and submit through the link in `docs/registration-confirmation.txt`. The form takes the SHA
  of the final HEAD (the commit after the tag, so that DEMO.md shows the live addresses) and
  the Fe version, `fe 26.7.0`.
