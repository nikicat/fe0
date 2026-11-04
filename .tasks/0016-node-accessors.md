---
status: todo
due: 2026-11-07
tags: [compiler]
---
# Named constructors and accessors for AST nodes

## Goal
Which of a node's slots `a`, `b`, `c` and `d` holds what is defined only by the comments on the
`NODE_` constants in `fe0/src/ast.fe`. The parser writes the slots (`n.b = 1`, `n.c = ...`), and
the test printer reads them (`n.b == 1`). The checker and codegen will be the third and fourth
readers. Four 0/1 flags (positional param, `mut` use, `var`, `true`) are bare `usize` values.
Done means every reader and writer goes through named constructors and accessors on `Node`, such
as `Node::param(pos, name, ty, positional: bool)`, `n.is_positional()`, `n.is_var()` and
`n.is_mut()`, and the slot comments shrink to those accessors.

## Decisions
- Planned rather than fixed in the parser commit: it touches every `NODE_` kind. Do it before
  the checker (T0004) starts reading nodes. From /unsmell run 20261104-221200, findings b1-9 and
  x-7 (`.git/unsmell/20261104-221200/findings/`).
- A separate `NODE_VAR` kind for `var` was judged not worth it (finding b2-8); an `is_var()`
  accessor names the flag instead.

## Next
List each kind's slots from `ast.fe`, and write one constructor and the accessors per kind.
