---
status: todo
tags: [tools, testing]
---
# Step 0: a differential harness on a node

## Goal
ADR 0016, step 0. Extend `tools/gas_compare.py` into a second differential harness that
deploys Fe's and Fe0's builds on anvil and compares, for each call: the success flag, the
return data, the logs, and the storage slots the call wrote. A call script line gains
`from=N`, the sender's account index. Steps 1, 3 and 4 (Tbrbh1, T3jcng, Tddgpr) are tested
with it. Done means it runs on the corpus in CI beside `embed.py` and reports no difference.
