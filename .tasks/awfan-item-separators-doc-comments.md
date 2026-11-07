---
status: todo
tags: [parser, spec, subset]
---
# Items on one line, and `///` inside a body

## Goal
Fe0 accepts two programs that Fe rejects with 1-0001:
- two items on one line, which SPEC.md §3's `program = { NL } { item { NL } }` allows;
- a `///` doc comment inside a block, which SPEC.md §1 says is ignored.

Done means: the grammar requires a newline between items, Fe0 rejects `///` where Fe does,
and there are reject probes for both.

## Next
Probe with `fe check` where Fe accepts `///`: before items, fields, variants and arms only,
or anywhere else too.
