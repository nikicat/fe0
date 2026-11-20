---
status: todo
tags: [conformance]
---
# Lexer gaps

## Goal
◐ and ❌ rows of SPEC.md §10 whose fix lives mostly in the Lexer and Back, which have room
(Lexer about 18.8 KB, Back about 7.4 KB under 24,576).
- Binary (`0b`) and octal (`0o`) literals, SPEC §1.
- `assert!` messages over 31 bytes: `Error(string)` over several words, §1.
- Widths that Fe lacks, such as `u7` and `u24`, as names, §1. Fe's type names are only
  `u8` to `u256` and `i8` to `i256` in powers of two, `usize`, `isize`, `bool` and `String`.
- `init`, `recv`, `assert`, `with` as identifiers, §1. This one costs Parser bytes, which
  are tight (about 1.9 KB left), so measure it first.
