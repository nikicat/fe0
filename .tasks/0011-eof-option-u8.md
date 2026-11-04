---
status: todo
tags: [compiler]
---
# End of input as `Option<u8>` instead of -1

## Goal
`Source::next_byte() -> i32` and `Lexer.peeked: i32` use -1 for end of input, compared as `< 0`
at several sites; a forgotten check could push it as byte 255. `Option<u8>` makes that
impossible.

## Next
Measure the cost first: the lexer costs about 800 gas per byte on the EVM. Use spike-lexer's
`lex_gas` pattern (DESIGN.md §8a), then decide. Findings b1-21, b2-6, x-3 of unsmell run
20261104-190143.
