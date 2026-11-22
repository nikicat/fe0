# 24. A newline token's span carries the last plain comment line

- Date: 2026-11-20
- Status: accepted

## Context
Fe rejects a plain comment line that comes last before the name of a variant or a field when
a doc comment or an attribute comes before it (SPEC §1, "A plain comment before a name"). The
subset rule ([0001](0001-strict-subset.md)) needs Fe0 to reject it too, so the parser must
know where the last plain comment line before a name starts. Plain comments make no tokens.

## Decision
A newline token's span runs from the first line break to the first byte of the last plain
comment line after it, if there is one. `Span.comment_line` in `fe0/src/lexer.fe` returns
where that line starts, and `Parser.no_comment_before_name` applies SPEC §1's rule with it.

## Alternatives
- **A comment token:** every parse site that reads a newline would have to skip it.
- **A flag on the token:** changes `Token` and its wire format.

## Consequences
- The span costs nothing on the wire.
- Five reject probes and `corpus/doc_comments.fe` pin the rule.
