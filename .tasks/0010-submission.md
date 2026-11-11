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

## Next
- README from the starter's SUBMISSION.md: pitch, problem, approach, Fe highlight (the effect
  check), architecture, build and test, demo, limitations, Fe0 spec link.
- The README's build and test section covers the native CLI: `fe build --backend native -e
  executable --out-dir out/cli fe0-cli`, then `out/cli/fe0_cli < program.fe`, its exit codes
  (0, 1, 2) and `tools/cli_check.py`. On an AArch64 Linux host it needs the patched Fe of
  WORKAROUNDS.md.
- Declaration: pre-existing work (everything before commit of Nov 3, see git log), reused code
  (none), AI assistance (most work AI-assisted, verified by probes and tests).
- Make the repo public (Apache-2.0 LICENSE is in place), record the exact commit SHA and
  `fe 26.5.1`.
