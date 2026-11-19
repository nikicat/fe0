# 10. The compiler reads its input through its own `Source` effect

- Date: 2026-11-04
- Status: accepted

## Context
The compiler must read source from stdin natively, from calldata on chain and from a string
under `fe test`. Fe's `std::io` is not stable across releases: Fe 26.5.1, 26.6.0 and 26.7.0
each read input through a different API.

## Decision
`fe0::io::Source` is fe0's own effect with one method, `next_byte`. The core uses only it.
Adapters in `fe0/src/io.fe` give a `Source` over `Bytes` or a string. The native CLI reads
stdin into `Bytes` and compiles from a `Source` over them.

## Alternatives
- **`std::io::Read`:** the core would need a port on each upgrade that changes it. Fe 26.6.0
  has no `Read` at all, only `Stdin` effects.

## Consequences
- Only the native CLI touches std I/O, so a change to `std::io` touches only the CLI.
