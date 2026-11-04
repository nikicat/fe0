# 13. No separate node kind for `var`

- Date: 2026-11-04
- Status: accepted

## Context
`let` and `var` share `NODE_LET`, with slot `c` set to 1 for `var`. The /unsmell review of the
parser (run 20261104-221200, finding b2-8) asked whether `var` deserves its own kind.

## Decision
Keep one kind. The flag gets a name through an `is_var()` accessor (T0016).

## Alternatives
- **`NODE_VAR`:** every reader of a binding would have to accept two kinds, for one bit of
  difference.
