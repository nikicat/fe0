---
status: todo
tags: [compiler]
---
# End of input as `Option<u8>` instead of -1

## Goal
`Source::next_byte() -> i32` and `Lexer.peeked: i32` use -1 for end of input, compared as `< 0`
at several sites; a forgotten check could push it as byte 255. `Option<u8>` makes that
impossible.

The lexer's 12 byte helpers (`is_digit`, `is_hex_digit`, `is_newline`, `is_escape`,
`unescape`, `digit_value` and the rest, `fe0/src/lexer.fe:410-470`) are free functions that
each take `c: i32`. Once end of input no longer shares the `i32`, make the byte a type with
these as its methods. Keep `Lexer.peeked` a plain value and wrap it where it is used, as
`Node.pos()` does: a struct field in a hot struct costs bytes under fe#1964
(docs/WORKAROUNDS.md).

## Next
Measure the cost first: the lexer costs about 800 gas per byte on the EVM. Use spike-lexer's
`lex_gas` pattern (DESIGN.md §8a), then decide. Findings b1-21, b2-6, x-3 of unsmell run
20261104-190143.
