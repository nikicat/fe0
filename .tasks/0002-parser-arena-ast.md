---
status: todo
due: 2026-11-05
tags: [compiler]
---
# Parser into the arena AST

## Goal
Recursive-descent parser for the Fe0 grammar (SPEC.md §3) producing the index-based arena AST
(DESIGN.md §3–4), with unit tests for each grammar rule and each `P` error.

## Decisions
- Arena: flat `MemVec`s of nodes, lists and syms, referenced by index (recursive types need
  `unsafe` in Fe).
- Precedence climbing with SPEC §3.2's table; no error recovery; first error wins.
- Cap nesting depth with a `P` "nesting too deep" error: the EVM stack limits recursion to
  about 1,019 calls (DESIGN.md §8a).

## Next
Write `ast.fe` (node kinds and field meanings), then `parser.fe`.
