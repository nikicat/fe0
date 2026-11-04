---
status: todo
tags: [upstream]
---
# Report the IR0600 compiler bug upstream

## Goal
Extracting the `Ok` payload of the lexer's old `Result<Diag, Lexed>` crashed codegen at -O1 and
above (WORKAROUNDS.md). File a minimal reproduction on argotorg/fe.

## Next
Minimize from `spike-harness/ice-lexer` (git-ignored, works at -O 0, fails at default). Check
master first; the issue text must not hint at the project.
