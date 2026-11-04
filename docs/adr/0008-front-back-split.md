# 8. Split the on-chain compiler into Front, Back and Compiler

- Date: 2026-10-28 (pre-window)
- Status: superseded by [0014](0014-contract-per-phase.md)

## Context
The spike lexer plus a dispatcher was 3.1 KB of runtime code. A full compiler was estimated at
8–15 times that, over the 24,576-byte limit of EIP-170. Contracts can pass `Bytes` to each
other, and a `Read` source can be fed from calldata `Bytes` (`spike-lexer/src/split.fe`).

## Decision
Three contracts: `Front` (lex, parse, check, then serialize the arrays), `Back` (codegen and
assembly) and a `Compiler` facade that calls both and deploys the result with `create_raw`.
Measure each phase early, and split again if one is too large.

## Consequences
The measurement (T0003) found the lexer and parser alone over the limit, so
[0014](0014-contract-per-phase.md) replaced this.
