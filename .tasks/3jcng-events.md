---
status: todo
deps: [Trvpxf]
tags: [spec, checker, codegen]
---
# Step 3: events

## Goal
ADR 0019. Top-level `#[event] struct` declarations with up to three `#[indexed]` fields,
`log: mut Log` in a contract's `uses`, and the fixed statement `log.emit(E { … })`, emitted as
`LOG1` to `LOG4` with topic 0 from `core::keccak`. Done means SPEC, checker, code generation, a
token corpus program that emits `Transfer`, the node harness comparing logs, and every phase
contract under 24,576 bytes.
