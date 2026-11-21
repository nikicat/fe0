---
status: todo
tags: [subset]
---
# A space before a record literal's `:`

## Goal
Fe 26.7.0 rejects a space or tab before the `:` of a field in a record literal, such as
`Data { first : n }`, with its error `1-0001` "missing closing `}` for record field list".
Fe0 accepts it. ADR 0001 requires Fe0 to reject every program that Fe 26.7.0 rejects, so this
is a subset bug. In Fe0, a record literal is an event's literal or the variant of a typed call,
such as `Other::Store { a: 1 }`. Fe accepts a space before every other `:`: in a `recv` arm's
pattern (`Go { t : t }`), a call's label (`g(a : n)`), a type annotation (`let q : u256`), a
parameter (`a : u256`) and a field of a struct's declaration.

Done means: Fe0 rejects the space or tab with a new error code, and SPEC.md states the rule. A
new reject program in `corpus/reject/` pins it, and Fe rejects that program too.

## State
- To reproduce it, put a space before the `:` of `first` in `corpus/events.fe`.
  `tools/mutate.py --seed 1 -n 20 --per-program 4` makes that mutant. CI runs other seeds
  (DESIGN.md §11a), and none of them makes it.
- Fe0 reads the record literal in `fe0/src/parser.fe` (`starts_record_literal`).
- The cause is a Fe bug, in Fe master `90d27f083` too. `RecordFieldScope` in
  `crates/parser/src/parser/expr_atom.rs` looks for a field's label with `peek_two()`, which
  skips trivia only before the first token. So `first : n` peeks as a name and then white
  space, and Fe parses `first` as the field's value. Reported as argotorg/fe#2057, with a
  proposed fix.

## Next
- Probe whether Fe also rejects a comment or a line break before the `:`.
- Make Fe0's parser reject what Fe rejects before the `:`, with a new parser (`P`) code in
  `fe0/src/diag.fe` and its message in `fe0-cli/src/messages.fe`. White space and comments make
  no token, so the parser sees either as a gap between the name's span and the `:`'s span. Then
  add the reject program and the SPEC.md rule.
