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
- README.md is written and reviewed, unstaged. Its gas table and ADR 0021's were remeasured on
  Fe 26.7.0 (whole corpus 1.51).
- The starter's SUBMISSION.md is gone, but the registration email lists what a submission must
  include: a public GitHub repository, the exact commit, an OSI license, the Fe version, tests,
  build instructions, a README, a demo and disclosures. The README covers all of them but the
  commit, which goes in the form.

## Next
- Redeploy every phase contract and Compiler from the submitted commit with `tools/deploy.py`
  and browser-web3-signer, then update docs/DEMO.md and `deployments/42161.json`. The Nov 14
  deployment already differs from main (since fb9d801).
- Push, make the repo public (Apache-2.0 LICENSE is in place), record the exact commit SHA and
  `fe 26.7.0`, and submit.
