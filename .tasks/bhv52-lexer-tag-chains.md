---
status: todo
tags: [lexer, size, unsmell]
---
# Tables instead of the lexer's long tag chains

## Goal
In `fe0/src/lexer.fe`, `Lexer.keyword` has 20 `if self.word(...)` branches, `Lexer.is_reserved`
23 `||` terms, and `Lexer.punct` about 25 `if c == C_X` branches. A table of (spelling, Tok)
pairs for keywords and reserved words, and a byte-to-Tok table for one-byte punctuation, each
scanned by one loop, would replace them. Done means: the tables are in, or a measurement shows
they cost bytes and the chains stay with a comment that says so.

## State
type_kind (unsmell b2-5, Nov 10): a (String<7>, Tok) table scanned by one loop cost +647 bytes
in LexProbe and +610 in CompileProbe at -O s, so type_kind stays a chain.

## Next
Measure `spike-sizes` CompileProbe (ADR 0014) before and after. A table may compile larger
than the chains, so the measurement decides.

Found by the /unsmell run of 2026-11-06 on T0006 (finding b2-8).
