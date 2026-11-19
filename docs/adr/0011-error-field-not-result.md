# 11. The lexer, the parser and the checker report errors in an `err` field, not a `Result`

- Date: 2026-11-04
- Status: accepted

## Context
With `lex()` returning `Result<Diag, Lexed>`, extracting the payload failed with the internal
compiler error IR0600 at `-O 1` and above. The trigger was `?` on a `Result<E, T>` inside a
`while true` loop, in a function whose own `Result` the caller then matches or unwraps.

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

## Update (2026-11-12, Fe 26.6.0)
IR0600 is gone in Fe 26.6.0. With `lex()` and `parse()` returning `Result`s, fe0's tests pass
at `-O 0`, `-O 1` and `-O s`. The fields stay because they make smaller code. The probes in
spike-sizes/ measure this at `-O s`.
- `parse() -> Result<Diag, Ast>` adds 733 to 845 bytes to ParseProbe. It adds about 2,600
  bytes to CompileProbe. `Ast` is large, and each step that moves it through a `Result` costs
  code.
- `lex() -> Result<Diag, Lexed>` alone saves 4 bytes in LexProbe. But then `Ast` would need an
  error case that is built without a `Lexed`. So this change does not pay on its own.

Each phase contract must be at most 24,576 bytes ([0014](0014-contract-per-phase.md)). The
decision stands, now for its size.

## Update (2026-11-19, Fe 26.6.0)
Code generation returns `Result<Diag, MemVec<u8>>`. It has no partial data to keep on error,
and its old `Output { code, err }` could hold code and an error at once. The `Result` made Back
136 bytes smaller and CompileProbe 85 bytes smaller (-O s). The lexer, the parser and the
checker keep their `err` fields.
