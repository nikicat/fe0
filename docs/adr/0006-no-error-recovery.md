# 6. No error recovery: the first error ends the compile

- Date: 2026-10-28 (pre-window)
- Status: accepted

## Context
The official parser recovers from errors to report several at once. Recovery costs code in every
phase, and Fe0 runs on chain, where bytecode size is the scarce resource
([0014](0014-contract-per-phase.md)). The input programs are small.

## Decision
Each phase stops at the first error and reports it with its code and position (DESIGN.md §9).

## Alternatives
- **Recovery with synchronizing tokens:** better for long programs, not worth its bytes here.

## Consequences
- Reject tests check exactly one diagnostic each.
- Later phases never see a partial AST, so they need no checks for missing parts.
