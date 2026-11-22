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
- Release `v0.1.1` is tagged and pushed, but not deployed. It makes Compiler's `deploy` revert
  when CREATE creates no contract; v0.1.0 returned the zero address, so a transaction with a
  tight gas estimate succeeded and created nothing. chain_check checks it with
  corpus/init_args.fe.
- Arbitrum One still runs v0.1.0, deployed on Nov 22 from e149684. DEMO.md and
  `deployments/42161.json` hold its addresses, and its demo passed.
- The playground (playground/README.md) is written and checked in jsdom on an anvil fork,
  against a v0.1.1 build, but not in a real browser. `.github/workflows/pages.yml` publishes it
  once Pages is on, with GitHub Actions as the source.
- README.md is written and reviewed. Its gas table and ADR 0021's were measured on Fe 26.7.0:
  over the whole corpus, Fe0's gas is 1.43 times that of Fe's build at `-O 1`.
- The registration email lists what a submission must include: a public GitHub repository, the
  exact commit, an OSI license, the Fe version, tests, build instructions, a README, a demo and
  disclosures. The README covers all of them but the commit, which goes in the form.

## Next
- Deploy v0.1.1: `rm deployments/42161.json`, run `tools/deploy.py` from the tag, then update
  the addresses and the demo transaction in docs/DEMO.md and commit them with the new
  `deployments/42161.json`. Try the playground in a browser against it.
- Nov 24: push, make the repo public (Apache-2.0 LICENSE is in place), turn on Pages, and
  submit through the link in `docs/registration-confirmation.txt`. The form takes the SHA of
  the final HEAD, the commit after the tag that gives DEMO.md the live addresses. It also takes
  the Fe version, `fe 26.7.0`.
