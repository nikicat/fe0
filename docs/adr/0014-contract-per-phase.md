# 14. One contract per compiler phase

- Date: 2026-11-04
- Status: accepted; supersedes [0008](0008-front-back-split.md)

## Context
A contract's runtime code may be at most 24,576 bytes. The phase contracts take about 64 KB in
all (DESIGN.md §8 gives each size), so the compiler spans several contracts.

Lexer and parser fit in one contract: a lexer + parser probe takes 21,454 bytes (Fe 26.7.0,
`-O s`). That leaves about 3.1 KB for the syntax that SPEC.md's "Fe0 and Fe at a glance"
marks ❌. A Parser contract of its own had about 7.5 KB of room at `-O s`, and has about
6.4 KB at `-O 1` (DESIGN.md §8).

## Decision
Each phase is its own contract, and a `Compiler` contract calls them in turn
(DESIGN.md §8). This leaves the Parser room to grow, and every boundary works alike. The
contracts are built as Sourcify rebuilds them, at `-O 1`
([ADR 0033](0033-verify-on-sourcify.md)).

## Alternatives
- **Lexer and parser in one contract:** fits, and saves one boundary, but leaves the Parser
  little room to grow.

## Consequences
- The Parser contract takes the lexer's tokens (`parse_lexed`), not the source.
- Each boundary serializes the arrays as words, which costs gas for every phase.
- An `Option` can cost the compiler's own bytecode. Code generation's label tables made the
  compile probe 919 bytes larger as `Option<Label>` than as a one-word `LabelSlot` whose id 0
  means empty (Fe 26.5.1, `fe0/src/asm.fe`).
- Keyword matching uses tables, to keep the Lexer small. The lexer looks up one packed word per
  identifier in a table (DESIGN.md §2), and one-byte punctuation in a byte table. Matching with
  `word<N>` is larger, because Fe instantiates it once per keyword length.
- A token kind is a `Tok` struct around a `u8`, not an `enum`. An `enum` crosses a contract
  boundary only through a `match` per variant, and that made each phase contract 1.8 to 2.5 KB
  larger (Fe 26.6.0, `-O s`). [WORKAROUNDS.md](../WORKAROUNDS.md) says when this can change.
- The Parser maps tokens to binding powers and token sets with code, not tables. Tables saved
  311 bytes, but made the code harder to read (Fe 26.6.0, `-O s`).
