---
status: todo
tags: [compiler, unsmell]
---
# Domain types instead of algebraic ones in fe0

## Goal
fe0 uses `Option`, `Result`, sentinels and bare `bool` where a named type would say what a
value means. Done means: each site below either has a domain type, or has a comment that
names the measured cost which keeps it as it is. Bytecode size and gas decide each case,
because every phase contract must stay under 24,576 bytes (ADR 0014).

## Sites (survey of Nov 11, on Fe 26.6.0)
- **End of input as -1.** `Source::next_byte() -> i32` (`fe0/src/io.fe`), `Lexer.peeked`,
  and the `C_*` byte constants that are `i32` only because of it (`fe0/src/lexer.fe:378`).
  End of input is compared as `< 0` at several sites, and a forgotten check could push it as
  byte 255. Use a named type, not `Option<u8>` (closed T0011 planned that): a byte case and an
  end case, with the 12 byte helpers (`is_digit`, `unescape`, …, `lexer.fe:410-470`) as
  methods of the byte. Fe 26.6.0's byte literals (`b'\n'`) can then replace the `C_*`
  constants. Keep `Lexer.peeked` a plain value and wrap it where it is used, as `Node.pos()`
  does: a field in a hot struct costs bytes under fe#1964 (docs/WORKAROUNDS.md). Unsmell
  run 20261104-190143, findings b1-21, b2-6 and x-3.
- **`err: Option<Diag>`** on `Lexed` (`lexer.fe:207`), `Ast` (`ast.fe:560`), `Checked`
  (`check.fe:84`) and `Output` (`codegen.fe:156`). Each phase's result is either its data or
  an error, so a phase result type fits. ADR 0011 chose the field because of an internal
  error in 26.5.1 (IR0600). WORKAROUNDS.md says how to check whether 26.6.0 still has it.
- **`Option<u256>` from `Text.int_value`** (`lexer.fe:292`). `None` means "over 256 bits".
- **`bool` parameters** of the node constructors: `positional` in `new_param`, `mutable` in
  `new_use` and `new_let` (`ast.fe:206`, `293`, `301`).
- **`Result<Diag, ()>`** in the checker (36 functions) and the parser (36). This is the
  error-propagation idiom with `?`, and probably stays. Decide it once, and write the reason
  down.

Not in scope: `LabelSlot` (`asm.fe:64`) is already a domain type. Its comment cites ADR 0014
for the 919 bytes that `Option<Label>` cost, and that is correct.

## Next
Start with the -1 sentinel. Measure the lexer's gas per byte (about 800 on the EVM, with
spike-lexer's `lex_gas` pattern, DESIGN.md §8a) and LexProbe's size (`spike-sizes/`,
`fe build -O s`), before and after. Then the phase results, after the IR0600 check.
