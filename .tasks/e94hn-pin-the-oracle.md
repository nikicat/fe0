---
status: todo
tags: [tools, testing]
---
# Pin the reference behaviour

## Goal
SPEC.md says Fe's behaviour is the reference, but Fe has a known miscompile at `-O 1` and
above (WORKAROUNDS.md), and the harness defaults to `-O 1`. The gas in the subset rule is
not stated either (`CALL_GAS` is a fixed 10M). Storage is checked only through the
contract's own reads, so a wrong slot layout that is consistent with itself passes.

Done means:
- the harness builds with Fe at `-O 0` and `-O 1`, and reports any difference between the
  two as a Fe bug, not as a Fe0 one;
- the anvil deploy gate compares raw storage slots (`eth_getStorageAt`) after each call;
- SPEC.md states the gas and the optimisation level that the rule refers to.
