# 11. The lexer, the parser and the checker report errors in an `err` field, not a `Result`

- Date: 2026-11-04
- Status: accepted

## Context
Each phase contract must be at most 24,576 bytes ([0014](0014-contract-per-phase.md)), so the
way a phase reports an error is a matter of code size. `Ast` is large, and each step that
moves it through a `Result` costs code.

## Decision
`Lexed`, `Ast` and the checker's output carry `err: Option<Diag>`. On error, the arrays hold
whatever was built before it.

Code generation returns `Result<Diag, DeployCode>`. It has no partial data to keep on error,
and a `Result` cannot hold code and an error at once.

Inside the lexer, the parser and the checker, a function that can fail returns
`Result<Diag, T>`, or `Result<Diag, ()>` when it has no value. Callers pass the error on with
`?`. These functions use `Result` itself, not a result type of their own, because a `?` after
each call is the shortest way to stop at the first error. Only the entry points report the
error in a field.

## Alternatives
The probes in `spike-sizes/` measure these on Fe 26.6.0 at `-O s`.
- **`parse() -> Result<Diag, Ast>`:** adds 733 to 845 bytes to ParseProbe, and about 2,600
  bytes to CompileProbe.
- **`lex() -> Result<Diag, Lexed>` alone:** saves 4 bytes in LexProbe. But then `Ast` would
  need an error case that is built without a `Lexed`, so the change does not pay on its own.
- **An `err` field on the output of code generation:** costs Back 136 bytes and CompileProbe
  85 bytes more than the `Result`.

## Consequences
- A caller must check `err` before reading the arrays of `Lexed`, `Ast` or the checker's
  output; nothing forces it to.
