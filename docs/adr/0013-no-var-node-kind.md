# 13. No separate node kind for `var`

- Date: 2026-11-04
- Status: accepted

## Context
`let` and `var` share `NODE_LET`, with slot `d` set to 1 for `var`. The /unsmell review of the
parser (run 20261104-221200, finding b2-8) asked whether `var` deserves its own kind.

## Decision
Keep one kind. The flag gets a name through an `is_var()` accessor (T0016).

## Alternatives
- **`NODE_VAR`:** every reader of a binding would have to accept two kinds, for one bit of
  difference.

## Update (2026-11-12)
The `mutable` flag of `new_use` and `new_let` stays a labeled `bool`. We measured a `Mutability`
type in its place. At `-O s` it cost 95 bytes in ParseProbe and 118 in CheckProbe (spike-sizes/).
The label at each call already says what the flag means.
