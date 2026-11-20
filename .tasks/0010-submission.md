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
- The submission includes the steps of ADR 0016 (Tf435j, Tbrbh1, Trvpxf, T3jcng, Tddgpr) that
  are done by Nov 24, and describes the rest as the plan. It also states the gas ratios of
  ADR 0021 by kind of program.

## Next
- README from the starter's SUBMISSION.md: pitch, problem, approach, Fe highlight (the effect
  check), architecture, build and test, demo, limitations (link SPEC.md §10, the Fe0 and Fe
  matrix), Fe0 spec link. The section "Fe0 as a subset to formalize" is already in README.md.
- The README's build and test section covers the native CLI: `fe build --backend native -e
  executable --out-dir out/cli fe0-cli`, then `out/cli/fe0_cli < program.fe`, its exit codes
  (0, 1, 2) and `tools/cli_check.py`.
- Declaration: pre-existing work (everything before commit of Nov 3, see git log), reused code
  (none), AI assistance (most work AI-assisted, verified by probes and tests).
- Redeploy every phase contract and Compiler from the submitted commit with `tools/deploy.py`
  and browser-web3-signer, then update docs/DEMO.md and `deployments/42161.json`. The Nov 14
  deployment already differs from main (since fb9d801).
- Make the repo public (Apache-2.0 LICENSE is in place), record the exact commit SHA and
  `fe 26.7.0`. The README explains the moves from 26.5.1 (ADRs 0015 and 0022).
