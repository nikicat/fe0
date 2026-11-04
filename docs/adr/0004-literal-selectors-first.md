# 4. Literal selectors first; `sol()` through a `Hasher` effect later

- Date: 2026-10-28 (pre-window)
- Status: accepted

## Context
`#[selector = sol("f()")]` needs keccak at Fe0's own run time. On 26.5.x, `core::keccak` and
`std::evm::keccak256` lower only on the EVM; natively they fail with "target does not support
EvmKeccak256". A first native probe seemed to work only because its input was constant, so the
hash was computed at compile time (`spike-native/probe_keccak.fe`). A software keccak in Fe is
feasible: one round over `[u64; 25]` matches a Python reference on both targets
(`spike-keccak/`), at about 28k gas per round on the EVM, so about 680k per permutation.

## Decision
Fe0 v1 accepts only literal selectors, `#[selector = 0x...]`. `sol("...")` is a stretch goal.
When it comes, hashing is an effect, `uses (h: mut Hasher)`: the EVM provider uses the
`KECCAK256` opcode, and the native provider is the software keccak-f[1600].

## Alternatives
- **Software keccak everywhere:** one code path, but 680k gas per hash makes on-chain compiles
  far more expensive.
- **No native build:** the native CLI is a goal of its own (T0008).

## Consequences
- DESIGN.md §12 holds the remaining work. Master has native keccak since #1909, but we stay on
  26.5.1 ([0009](0009-freeze-on-26-5-1.md)).
