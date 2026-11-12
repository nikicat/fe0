---
status: todo
tags: [codegen, unsmell]
---
# Repeated shapes in code generation, and one doc fact stated twice

## Goal
Smells that the /unsmell run of 2026-11-12 (run 20261112-165434) found on lines the caller
work did not change. Each is fixed, or measured and kept with a reason, because bytecode size
decides (ADR 0014).

## Next
- `fe0/src/codegen.fe`: `self.asm.jumpi(self.stub(X))` is written 8 times. A `Gen` method such
  as `jumpi_to(stub)` would name it, and may shrink bytecode (finding b4-3).
- `fe0/src/codegen.fe`: "set FP" (`push FP; MSTORE`) is written 3 times. A `set_fp` method next
  to `fp` would own it (b4-4).
- `fe0/src/codegen.fe`: "store word k of the revert data" is written 4 times. A
  `store_revert_word` method would own it (b4-5).
- `fe0/src/codegen.fe`: every walk over a child list is a hand-written index loop (8 sites).
  An iterator over a `ListId` would replace them. Measure first, since iterators may cost
  bytecode (b4-6).
- `fe0/src/ast.fe`: the module doc (lines 5-6) and the `Ty` doc both say what `ty()` holds.
  The `Ty` doc owns it, and the module doc drops its last sentence (b2-7).

The findings and their reasons are in `.git/unsmell/20261112-165434/findings/` while that run
directory exists.
