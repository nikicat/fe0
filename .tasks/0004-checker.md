---
status: doing
deps: [T0002, T0016]
due: 2026-11-09
tags: [compiler]
---
# Checker: names, types, constants and effects

## Goal
Implement SPEC.md §5–6 and DESIGN.md §5: name resolution, types, compile-time constants, and the
`uses` effect check (the Fe-specific highlight). One accept and one reject test per rule, with
error code and position. Error codes as in `fe0/src/diag.fe`.

## State
`fe0/src/check.fe` checks every rule of SPEC §5–6, and `fe0/src/check_tests.fe` has an accept
and a reject case per rule, each with its code and byte offset. `tools/gen_check_tests.py`
generates the tests. All 31 tests pass at `-O 0` and at the default level, including the
parser's deepest nesting. Lexer, parser and checker together are 39,767 runtime bytes at `-O s`,
so the checker alone is about 15 KB.

## Next
Not covered yet. Each one is small:
- unused `uses` entries are not reported (SPEC §6 wants a warning, and `Diag` has no warnings);
- duplicate selectors, and selectors over 32 bits, are not rejected.
