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
- Arbitrum One runs release v0.1.2 (ba1e2e2, tagged and pushed), deployed on Nov 22.
  `deployments/42161.json` and docs/DEMO.md hold its addresses. The five contracts were
  created in one transaction (13,797,200 gas), and the demo deployed the counter (2,103,335
  gas), whose `get()` returns 2. Compiler's `deploy` reverts when CREATE creates no contract,
  which tools/chain_check.py checks with corpus/init_args.fe.
- The playground (playground/README.md) is written and checked in jsdom on an anvil fork,
  against a v0.1.1 build, whose contracts differ from v0.1.2's only in `version()`. It is not
  checked in a real browser yet. `.github/workflows/pages.yml` publishes it once GitHub Pages
  is on, with GitHub Actions as the source.
- README.md is written and reviewed. Its gas table and ADR 0021's were measured on Fe 26.7.0:
  over the whole corpus, Fe0's gas is 1.43 times that of Fe's build at `-O 1`.
- The registration email lists what a submission must include: a public GitHub repository, the
  exact commit, an OSI license, the Fe version, tests, build instructions, a README, a demo and
  disclosures. The README covers all of them but the commit, which goes in the form.

## Next
- Commit docs/DEMO.md and `deployments/42161.json`. Try the playground in a browser against
  the v0.1.2 Compiler.
- Nov 24: push, make the repo public (Apache-2.0 LICENSE is in place), turn on Pages, and
  submit through the link in `docs/registration-confirmation.txt`. The form takes the SHA of
  the final HEAD, the commit after the tag that gives DEMO.md the live addresses. It also takes
  the Fe version, `fe 26.7.0`.
