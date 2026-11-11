---
status: todo
tags: [spec, checker, future]
---
# Sized integer types

## Goal
Fe0 has one integer type, `u256` (SPEC.md §2). Fe also has `u8` to `u128` and the signed
`i8` to `i256`. Adding them, or some of them, would let more Fe programs be Fe0 programs. Done
means: SPEC.md defines the added types and their operations, the checker types and checks
them, the code generator masks, extends and checks overflow per width, and the differential
tests cover each width against the official compiler.

## Decisions
- The literal range check moves with this task. Today a literal only has to fit in 256 bits.
  So `Parser.int_word` checks it, as the literal's own rule, and reports `L004`. With sized
  types, the range depends on the literal's type, as in Fe (`8-0074`, "integer literal out of
  range"). The check then belongs in the checker, after the literal's type is known. That also
  gives Fe's error order, where every syntax error comes before an out-of-range literal.

## Next
Decide the scope first: which widths, and whether signed types are in. Then measure what one
more width costs in the on-chain compiler (DESIGN.md §8). Each phase contract must stay under
the 24,576-byte limit (ADR 0014).

Raised during the /unsmell run of 2026-11-10 (finding b2-4, where the range check moved).
