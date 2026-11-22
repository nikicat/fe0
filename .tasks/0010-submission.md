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
- Code is frozen. Release `v0.1.0` is the tag on e149684. tools/deploy.py deployed it to
  Arbitrum One on Nov 22, and its demo passed: `version()` returns "0.1.0", and counter.fe
  deployed through Compiler returns 2. DEMO.md and `deployments/42161.json` have the new
  addresses, and DEMO.md's commands were run against them.
- README.md is written and reviewed. Its gas table and ADR 0021's were remeasured on
  Fe 26.7.0 (whole corpus 1.43).
- The starter's SUBMISSION.md is gone, but the registration email lists what a submission must
  include: a public GitHub repository, the exact commit, an OSI license, the Fe version, tests,
  build instructions, a README, a demo and disclosures. The README covers all of them but the
  commit, which goes in the form.

## Next
- A fix from now on needs a new release (v0.1.1) and a new deploy.
- Nov 24: push the branch and the tag, make the repo public (Apache-2.0 LICENSE is in place),
  and submit through the link in `docs/registration-confirmation.txt`. The form takes the SHA
  of the final HEAD (the commit after the tag, so that DEMO.md shows the live addresses) and
  the Fe version, `fe 26.7.0`.
