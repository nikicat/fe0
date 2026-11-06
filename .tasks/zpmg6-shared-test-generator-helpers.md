---
status: todo
tags: [tools, unsmell]
---
# Shared helpers for the test generators

## Goal
`tools/gen_check_tests.py` and `tools/gen_codegen_tests.py` repeat the `fe` path from argv,
the `lit()` string escaper, the write-then-`fe fmt` ending, and an else-if chain longer than
the parser's `MAX_DEPTH`. The depths that `gen_codegen_tests.py` names
(`DEEPEST_PARENS_IN_ARM`, `DEEPEST_BLOCKS_IN_ARM`) also mirror `parser_tests.fe`'s
`DEEPEST_PARENS`/`DEEPEST_BLOCKS`. Move the shared parts into one module, such as
`tools/fegen.py`. T0006's `embed.py` will want the same helpers.

Found by the /unsmell run of 2026-11-05 on T0005 (findings x-16, x-17).
