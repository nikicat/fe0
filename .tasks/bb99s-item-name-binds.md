---
status: todo
tags: [checker, subset]
---
# Reject locals and binds named like items

## Goal
Fe0 miscompiles a recv bind named like a constant. With `const n: u256 = 5`, the arm
`Set { a: n } -> u256 { n + 100 }` builds differently: Fe0 binds `n`, while Fe seems to
match it against the constant as a pattern. `let n: u256 = 2` is accepted by Fe0 and rejected
by Fe (8-0101, refutable pattern). `declare` in `fe0/src/check.fe` rejects only field names
and uppercase names.

Done means: Fe0 rejects a local, parameter or bind whose name is a constant's, and any other
item name for which Fe disagrees. SPEC.md §5.2 states the rule, and there is a reject probe for
each form.

## Next
- Probe with `fe check` which item kinds matter (constant, function, msg, contract) for each of
  let, var, parameter and bind.
- Probe programs from the review are kept in `p/constlocal.fe`, `p/constparam.fe` and
  `p/shconst.fe` in the job's tmp directory, which is temporary.
