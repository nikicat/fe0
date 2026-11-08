---
status: todo
tags: [parser, docs]
---
# Grammar comments in the parser drift from SPEC

## Goal
Each parsing function in `fe0/src/parser.fe` carries its own copy of its SPEC.md §3.1
grammar rule, such as `// variant = selector NL IDENT …`. The copies drift. When the
doc-comment work (task Tawfan) required a newline after a selector, the comment on `variant`
went stale. Done means: one source of truth for the grammar, with no copy that can drift.

## Options
- Keep the copies, and add a test or script that checks each `// rule = …` comment against
  the EBNF block in SPEC §3.1.
- Replace each copy with a pointer, such as `// SPEC §3.1, rule variant.`

## Ruled out
- Nothing yet.
