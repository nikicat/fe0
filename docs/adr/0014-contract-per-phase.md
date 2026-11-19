# 14. One contract per compiler phase

- Date: 2026-11-04
- Status: accepted; supersedes [0008](0008-front-back-split.md)

## Context
Measured on Fe 26.5.1 (`spike-sizes/`, probes that take the source as `bytes` calldata).
Runtime bytes:

| Probe | `-O 0` | `-O 1` | `-O 2` | `-O s` |
|---|---|---|---|---|
| empty (ABI decode only) | | | | 182 |
| lexer | 18,441 | 7,583 | 7,580 | 7,511 |
| lexer + parser | 54,014 | 27,365 | 27,301 | 26,456 |
| lexer + parser + checker (Nov 5) | | | | 41,500 |
| the whole compile, with code generation (Nov 5) | | | | 54,668 |

Lexer and parser together are already over 24,576 bytes. On anvil the lexer probe deploys and
the lexer + parser probe is rejected (status 0). So `Front` of [0008](0008-front-back-split.md)
does not fit. The parser alone is about 19 KB, the checker about 15 KB and code generation
about 13 KB.

## Decision
Each phase is its own contract, and a `Compiler` contract calls them in turn
(DESIGN.md §8). Builds use `-O s`.

## Alternatives
- **Shrink lexer and parser to fit one contract:** 2.5 KB to cut, and the checker would still
  need a contract of its own.

## Consequences
- The parser needs an entry point that takes a `Lexed`; `parse()` lexes for itself today.
- Each boundary serializes the arrays as words, which costs gas for every phase.
- An `Option` can cost the compiler's own bytecode. Code generation's label tables made the
  compile probe 919 bytes larger as `Option<Label>` than as a one-word `LabelSlot` whose id 0
  means empty (`fe0/src/asm.fe`).
- If a phase outgrows 24 KB, the cheapest cut found so far is keyword matching: `word<N>` is
  instantiated once per keyword length, and `keyword` plus `is_reserved` are among the largest
  functions in the IR. Update, Nov 15: keyword matching no longer uses `word<N>`. The lexer
  looks up one packed word per identifier in tables (DESIGN.md §2), and one-byte punctuation
  in a byte table. The punctuation table alone cut 364 bytes. Together they cut the Lexer
  contract's runtime code from 7,685 to 6,031 bytes on Fe 26.6.0 at `-O s`.
