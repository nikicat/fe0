---
status: todo
tags: [tests, unsmell]
---
# Fold `Printer.span` into `Printer.sym`

## Goal
In `fe0/src/parser_tests.fe`, `Printer.span` became one call,
`self.out.extend_from_slice(self.ast.lexed.text.span_bytes(s))`, and its only caller is
`Printer.sym`, which looks up the span and passes it on. Done means `sym` writes the bytes
itself and `span` is gone. Test code only, so no contract bytecode changes.

## Next
Put the body into `sym` with `self.ast.span_of(s)` as the span, delete `span`, and run
`fe test` in `fe0/`.

Found by the third re-check of the /unsmell run of 2026-11-12 (finding r3-1). The run stops
after three re-checks, so this was planned instead of fixed.
