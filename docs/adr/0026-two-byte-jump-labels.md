# 26. Jumps always push 2-byte labels, assembled in one pass

- Date: 2026-10-28 (pre-window)
- Status: accepted

## Context
The assembler (`Asm` in `fe0/src/asm.fe`) records each use of a label as
`(byte_offset, label)` in a fixup list and patches every fixup when it finishes.

## Decision
Every jump pushes its label with `PUSH2`. The 2-byte targets keep offsets stable, so the
assembler runs a single pass with no relaxation.

## Alternatives
- **Relaxation:** a push as short as its target allows. A shorter push changes the offsets
  after it, so this needs more passes.

## Consequences
- Code must stay under 64 KB (`MAX_CODE` in `fe0/src/asm.fe`). `generate` in
  `fe0/src/codegen.fe` reports code of 64 KB or more as `G002`. A chain accepts at most
  49,152 bytes of initcode (EIP-3860), so the limit does not bind a deployable program.
- A jump to a target below 256 takes one byte more than it would with `PUSH1`.
