# 5. The AST is an index-based arena

- Date: 2026-10-28 (pre-window)
- Status: accepted

## Context
Fe has recursive types only through raw `*T`, which needs `unsafe` (found by the Oct 27 lexer
spike). A tree of boxed nodes is therefore not an option. Measured on the EVM
(`spike-limits/`), `MemVec` growth is linear: 851–902 gas per item across three interleaved
vectors, so about 1M gas for the AST of a 2 KB program.

## Decision
Nodes live in flat `MemVec`s and refer to each other by index, with index 0 meaning "none".
A child list is a length-prefixed run in one array. Check results go into side tables indexed
by node, and the AST is never mutated after parsing. `fe0/src/ast.fe` declares the layout.

## Alternatives
- **`unsafe` pointers:** possible, but unsafe code in a compiler meant to be formalized is the
  wrong signal, and it buys nothing for programs of a few KB.

## Consequences
- The arrays serialize trivially as words, which the on-chain split needs
  ([0014](0014-contract-per-phase.md)).
- What each slot of a node holds is a convention, not a type. Named constructors and
  accessors (T0016) keep the readers honest.
