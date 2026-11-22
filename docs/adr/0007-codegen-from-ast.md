# 7. Generate EVM code straight from the AST, with frames in memory

- Date: 2026-10-28 (pre-window)
- Status: accepted

## Context
The official compiler lowers through HIR, MIR and Sonatina IR. Fe0 has three types, no generics
and no references, and it must fit on chain ([0014](0014-contract-per-phase.md)).

## Decision
Code generation walks the AST and emits EVM opcodes as a stack machine, with no IR. Locals and
parameters live in memory frames at fixed offsets from a frame pointer (DESIGN.md §6). The
assembler resolves labels in one pass with fixed 2-byte jump targets (DESIGN.md §7).

## Alternatives
- **An IR with optimization passes:** smaller and cheaper output, but a second compiler's worth
  of code and tests within three weeks.
- **Locals on the EVM stack:** cheaper, but `DUP16`/`SWAP16` limit how many live values a
  function can have.

## Consequences
- The EVM stack bounds the recursion of generated code
  ([0023](0023-frame-pointer-on-the-stack.md)). The compiler itself has a separate depth limit
  ([0012](0012-max-depth.md)).
- Output is larger and more expensive than the official compiler's. The harness compares
  behaviour, not size.
