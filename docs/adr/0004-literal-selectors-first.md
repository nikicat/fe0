# 4. Literal selectors first; `sol()` through a `Hasher` effect later

- Date: 2026-10-28 (pre-window)
- Status: accepted; its `Hasher` part is superseded by [0015](0015-move-to-26-6-0.md)

## Context
`#[selector = sol("f()")]` needs keccak at Fe0's own run time, both on chain and in the native
CLI. A literal selector needs no hashing at all.

## Decision
Fe0 v1 accepts only literal selectors, `#[selector = 0x...]`. `sol("...")` is a stretch goal,
and DESIGN.md §12 holds the work it needs.

**Superseded by [0015](0015-move-to-26-6-0.md):** hashing goes through a `uses (h: mut Hasher)`
effect. The EVM provider uses the `KECCAK256` opcode, and the native provider is a software
keccak-f[1600]. The reason was that on Fe 26.5.x, `core::keccak` and `std::evm::keccak256`
lowered only on the EVM. Natively they failed with "target does not support EvmKeccak256".

## Alternatives
- **Software keccak everywhere:** one code path, but `spike-keccak/` measured about 28k gas
  per round on the EVM, so about 680k per permutation (Fe 26.5.x). That makes on-chain
  compiles far more expensive.
- **No native build:** the native CLI is a goal of its own (T0008).

## Consequences
- Programs that use `sol("...")` selectors do not compile with Fe0 until the stretch goal is
  done.
