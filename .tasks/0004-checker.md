---
status: todo
deps: [T0002, T0016]
due: 2026-11-09
tags: [compiler]
---
# Checker: names, types, constants and effects

## Goal
Implement SPEC.md §5–6 and DESIGN.md §5: name resolution, types, compile-time constants, and the
`uses` effect check (the Fe-specific highlight). One accept and one reject test per rule, with
error code and position. Error codes as in `fe0/src/diag.fe`.
