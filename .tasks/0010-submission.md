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
- The deployed compiler predates 06ee1b4, which accepts chained comparisons such as
  `a < b == true`, and it has no `version()`. So redeploy before submission: commit, tag
  `v0.1.0` (fe0-chain/README.md, "Releases"), remove `deployments/42161.json` (deploy.py refuses a file
  from another release), run `tools/deploy.py`, then update the addresses in docs/DEMO.md and
  commit them with the new `deployments/42161.json`. Push the tag with the branch.
- Push, make the repo public (Apache-2.0 LICENSE is in place), record the exact commit SHA and
  `fe 26.7.0`, and submit with the link in `docs/registration-confirmation.txt`.
