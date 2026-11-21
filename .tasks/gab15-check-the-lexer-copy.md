---
status: todo
tags: [tools]
---
# Check the tools' copy of Fe0's lexer

## Goal
The tools copy Fe0's lexer rules (`fe0/src/lexer.fe`) by hand. `tools/fetokens.py` has the
operators, in its `Op` enum and its token regex `_TOKEN`, and the assignment operators in
`ASSIGN_OPS`, which copies `Tok.is_assign`. `tools/mutate.py` has the binary operators in
`BINARY_OPS`, which copies `Tok.is_binary`. Nothing checks the copy. An operator added to the
lexer but not to the copy would make the mutations (DESIGN.md §11a) and
`tools/newline_check.py`, which adds line breaks to programs, miss places to change or pick
wrong ones, and no check would fail.

Done means: a check, run in CI, compares the tokens of each corpus program, as `fetokens.py`
reads them without white space and comments, with Fe0's own token stream. It also compares the
set of operators of Fe0's lexer with `Op`, and for each operator, including those that no corpus
program uses, whether the tools and Fe0 take it as binary (`Tok.is_binary`) and as an assignment
(`Tok.is_assign`).

## Next
- The native CLI (`fe0-cli`) cannot print its tokens. Add a flag that prints each token's
  kind and span, and one that prints the lexer's operators with `Tok.is_binary` and
  `Tok.is_assign` of each. Then write the check.
