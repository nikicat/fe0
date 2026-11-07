---
status: todo
tags: [lexer, spec, subset]
---
# Newlines in a block inside parentheses

## Goal
The lexer drops every newline while `paren_depth > 0` (`fe0/src/lexer.fe`), and SPEC.md
§3.4 states that rule. Fe does not drop them inside a `{ }` block nested in the parentheses:
- `({ g` + newline + `(1) })` is the call `g(1)` in Fe0 and two statements in Fe, so the
  builds differ.
- `({ return` + newline + `5 })` is accepted by Fe0 as `return 5` and rejected by Fe (8-0013).

Done means: the lexer drops a newline only when the innermost open bracket is `(` (or `[`, if
Fe agrees). SPEC.md §3.4 says so, and reject and corpus programs cover both cases.

## Next
- Probe how Fe reads newlines in `[ ]` and in `{ }` inside `( )`.
- Replace the depth counter with a small bracket stack, bounded like `MAX_DEPTH`.
- Related: T0014 (parser differential for the newline rule).
