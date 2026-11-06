---
status: todo
tags: [tools, unsmell]
---
# Shared helpers for the test generators

## Goal
`tools/gen_codegen_tests.py` names the deepest nesting the parser accepts inside an arm
(`DEEPEST_PARENS_IN_ARM`, `DEEPEST_BLOCKS_IN_ARM`), which mirrors `parser_tests.fe`'s
`DEEPEST_PARENS`/`DEEPEST_BLOCKS` and so the parser's `MAX_DEPTH`. Derive both from one place.

Found by the /unsmell run of 2026-11-05 on T0005 (findings x-16, x-17).

## State
T0006 moved the rest into `tools/fegen.py`: the `fe` path (`$FE`), `lit`, `write_formatted`,
`CHAIN_LEN`, and the payloads and test function of the differential tests.
