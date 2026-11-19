# 14. One contract per compiler phase

- Date: 2026-11-04
- Status: accepted; supersedes [0008](0008-front-back-split.md)

## Context
A contract's runtime code may be at most 24,576 bytes. Measured on Fe 26.5.1 (`spike-sizes/`,
probes that take the source as `bytes` calldata), runtime bytes:

| Probe | `-O 0` | `-O 1` | `-O 2` | `-O s` |
|---|---|---|---|---|
| empty (ABI decode only) | | | | 182 |
| lexer | 18,441 | 7,583 | 7,580 | 7,511 |
| lexer + parser | 54,014 | 27,365 | 27,301 | 26,456 |
| lexer + parser + checker | | | | 41,500 |
| the whole compile, with code generation | | | | 54,668 |

Lexer and parser together are over the limit. On anvil the lexer probe deploys and the lexer +
parser probe is rejected (status 0). So `Front` of [0008](0008-front-back-split.md) does not
fit. The parser alone is about 19 KB, the checker about 15 KB and code generation about 13 KB.

## Decision
Each phase is its own contract, and a `Compiler` contract calls them in turn
(DESIGN.md §8). Builds use `-O s`.

## Alternatives
- **Shrink lexer and parser to fit one contract:** 2.5 KB to cut, and the checker would still
  need a contract of its own.

## Consequences
- The Parser contract takes the lexer's tokens (`parse_lexed`), not the source.
- Each boundary serializes the arrays as words, which costs gas for every phase.
- An `Option` can cost the compiler's own bytecode. Code generation's label tables made the
  compile probe 919 bytes larger as `Option<Label>` than as a one-word `LabelSlot` whose id 0
  means empty (Fe 26.5.1, `fe0/src/asm.fe`).
- Keyword matching uses tables, to keep the Lexer small. The lexer looks up one packed word per
  identifier in a table (DESIGN.md §2), and one-byte punctuation in a byte table. Matching with
  `word<N>` is larger, because Fe instantiates it once per keyword length.
