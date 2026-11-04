---
status: todo
deps: [T0004]
due: 2026-11-14
tags: [compiler]
---
# Code generation, assembler and dispatcher

## Goal
AST to EVM bytecode per DESIGN.md §6–7: memory frames and calling convention, checked operators
with the official panic payloads, the dispatcher and deployment layout matching the official
compiler (SPEC.md §6), and a one-pass assembler with 2-byte jump targets. The first differential
tests pass.
