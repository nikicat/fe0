---
status: todo
deps: [T0005]
due: 2026-11-18
tags: [native]
---
# Native CLI (`fe0-cli`)

## Goal
A native executable that reads Fe0 source on stdin and prints the bytecode as hex. It is the
only place that touches std I/O (26.5.1's `std::io`; master removed it, see WORKAROUNDS.md).
Its output must match the on-chain compile byte for byte.
