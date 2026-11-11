---
status: todo
tags: [tools, types, unsmell]
---
# Types for the unit-test generators

## Goal
`tools/fegen.py`, `embed.py`, `gen.py` and `cli_check.py` are fully annotated, use domain types
for their `str` and `int` values (`FeSource`, `FeLine`, `FeName`, `Selector`, `Word`, `Wei`, …),
and pass `mypy --strict` and `pyright` with 0 errors. `tools/gen_codegen_tests.py` and
`tools/gen_check_tests.py` are not. They still pass plain `str` and `int` into the typed fegen
API (`Deploy`, `Call`, `DiffTest`, `write_formatted`, `lit`), and mypy reports about 14
arg-type errors in them. Done means: both are annotated with the same domain types, and the
checkers report 0 errors on all six tools.

## Next
From `tools/`, run `uvx mypy --strict gen_codegen_tests.py gen_check_tests.py` and
`uvx pyright` on them, and wrap each value at the place where it is made. Then check that the
regenerated `fe0/src/codegen_tests.fe` and `check_tests.fe` are byte-identical. Both also
join their lines into a module by hand. They should use fegen's function for that (unsmell
re-check finding rc1-3).

Found by the /unsmell run of 2026-11-10 on T0008 (change c19).
