# 11. Phases report errors in an `err` field, not a `Result`

- Date: 2026-11-04
- Status: accepted

## Context
With `lex()` returning `Result<Diag, Lexed>`, extracting the payload failed with the internal
compiler error IR0600 at `-O 1` and above. WORKAROUNDS.md records the details.

## Decision
`Lexed` and `Ast` carry `err: Option<Diag>`. On error, the arrays hold whatever was built
before it. Later phases follow the same shape.

## Alternatives
- **Keep `Result` and test only at `-O 0`:** deployed code is built optimized, so the failing
  configuration is the one that matters.

## Consequences
- A caller must check `err` before reading the arrays; nothing forces it to.
- IR0600 is fixed on master, so revisit this only if we leave 26.5.1
  ([0009](0009-freeze-on-26-5-1.md)).
