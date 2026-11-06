---
status: todo
tags: [compiler, unsmell]
---
# Distinct types for node ids and list ids

## Goal
Node ids and list ids are both plain `usize` across `fe0/src/ast.fe`, `check.fe` and
`codegen.fe`, and functions take them side by side (`Gen.index_of(l, i)`, `elem(l, k)`), so
they are easy to swap. Give each a one-word wrapper type, as `asm::LabelSlot` does for labels,
if the wrappers cost no bytecode (measure with `spike-sizes` `CompileProbe`, ADR 0014).

Found by the /unsmell run of 2026-11-05 on T0005 (finding b1-19).
