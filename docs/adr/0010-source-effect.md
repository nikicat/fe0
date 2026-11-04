# 10. The compiler reads its input through its own `Source` effect

- Date: 2026-11-04
- Status: accepted

## Context
The compiler must read source from stdin natively, from calldata on chain and from a string
under `fe test`. The spike used `std::io::Read`, but master removes character I/O from
`std::io` (`Read`, `read_char`, `host()`), replacing it with `Stdin` effects.

## Decision
`fe0::io::Source` is fe0's own effect with one method, `next_byte`. The core uses only it.
Adapters in `fe0/src/io.fe` give a `Source` over `Bytes` or a string; the native CLI will give
one over stdin.

## Alternatives
- **`std::io::Read`:** works on 26.5.1, but the core would need a port as soon as we left it.

## Consequences
- The core passes on both 26.5.1 and master. Only the native CLI touches std I/O.
