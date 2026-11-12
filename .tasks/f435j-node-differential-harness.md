---
status: doing
tags: [tools, testing]
---
# Step 0: a differential harness on a node

## Goal
ADR 0016, step 0. Extend `tools/gas_compare.py` into a second differential harness that
deploys Fe's and Fe0's builds on anvil and compares, for each call: the success flag, the
return data, the logs, and the storage slots the call wrote. A call script line gains
`from=N`, the sender's account index. Steps 1, 3 and 4 (Tbrbh1, T3jcng, Tddgpr) are tested
with it. Done means it runs on the corpus in CI beside `embed.py` and reports no difference.

## State
`tools/node.py` (anvil, builds, a `Run` per transaction from the call and prestate tracers),
`tools/node_check.py` (the comparison) and `from=N` in call scripts are committed.
`gas_compare.py` uses `node.py` and gives the same numbers as before. On the corpus against
Fe -O 1, 41 of 45 programs agree. The other 4 differ in storage writes, because Fe 26.6.0
packs narrow fields and Fe0 does not (Trcr1j). The CI step that runs node_check after the native CLI
check waits for that fix.

## Next
After Trcr1j: add the CI step (`uv run --project tools --locked tools/node_check.py` after `tools/cli_check.py` in
`.github/workflows/ci.yml`), and run node_check on the generated programs too.

## Follow-ups (unsmell run 20261112-110245)
- The extra-byte count of a call-script entry is a bare `int` in `Args.extra`, `Deploy`,
  `Call`, `push_words` and `encode_words` (tools/embed.py, tools/fegen.py), while the value
  and the sender have NewTypes. An `ExtraBytes` NewType in fegen would say what it counts
  (finding b2-9).
