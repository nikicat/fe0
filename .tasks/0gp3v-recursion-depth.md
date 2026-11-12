---
status: todo
tags: [checker, codegen, subset]
---
# Recursion depth differs from Fe

## Goal
Fe keeps return addresses on the EVM stack, and Fe0 keeps frames in memory. A recursive
`f(n) = if n == 0 { 0 } else { f(n - 1) }` behaves the same up to n = 1010 and differently
from n = 1020. DESIGN.md §8a presents "no such limit" as a feature, but it breaks the
subset rule's promise of the same behaviour.

Done means one of:
- Fe0 rejects recursive call cycles (a call-graph check in the checker), or
- SPEC.md qualifies the subset rule: the same behaviour below Fe's stack limit, and given
  enough gas.

## Decisions
- Rejecting cycles keeps the rule exact, and it is allowed by the subset rule. Check first
  whether any corpus program or planned demo needs recursion.
- ADR 0021 (accepted Nov 12) chooses the second option: SPEC.md qualifies the subset rule
  below Fe's stack limit, and recursive cycles stay allowed. The work
  is the SPEC sentence and a note in DESIGN.md §8a.
