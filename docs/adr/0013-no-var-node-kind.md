# 13. No separate node kind for `var`

- Date: 2026-11-04
- Status: accepted

## Context
`let` and `var` share `NODE_LET`, with slot `d` set to 1 for `var`. The question is whether
`var` deserves its own node kind, and whether the `mutable` flag of `new_use` and `new_let`
deserves its own type.

## Decision
Keep one kind. The flag gets a name through an `is_var()` accessor. The `mutable` flag of
`new_use` and `new_let` stays a labeled `bool`, because the label at each call already says
what the flag means.

## Alternatives
- **`NODE_VAR`:** every reader of a binding would have to accept two kinds, for one bit of
  difference.
- **A `Mutability` type in place of the `bool`:** at `-O s` it cost 95 bytes in ParseProbe and
  118 in CheckProbe on Fe 26.6.0 (`spike-sizes/`).
