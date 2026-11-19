---
status: todo
tags: [compiler, size, unsmell]
---
# Checker.item_of through Checked.narrow

## Goal
`Checker.item_of` (fe0/src/check.fe) writes the rule of `Checked.narrow` out by hand
(`self.node(d).kind != K::kind()`), with no comment saying why. `read`, `call`, `eval` and
`Gen.load` call `narrow`. Done means `item_of` calls `self.c.narrow<K>(decl(d))`, or keeps the
hand-written test with a measured comment, as `Checker.assign` does.

## Next
Make the change and measure the Checker with `tools/chain_check.py` (Fe 26.7.0, -O s). Keep it
only if the Checker does not grow.

Found by unsmell run 20261119-211753 (finding recheck-1-13).
