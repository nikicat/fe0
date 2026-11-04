# 1. Fe0 is a strict subset of Fe, stricter where Fe is permissive

- Date: 2026-10-28 (pre-window)
- Status: accepted

## Context
The Fe team wants a Fe subset small enough to formalize in Lean, and two judges are Fe core
developers. A subset that drifts from Fe, or has corners its spec doesn't pin down, would not
survive their review. Checking SPEC.md draft 0 against the official compiler (`spike-conform/`:
23 compile-time and 15 run-time probes) found places where Fe is more permissive than the
draft: forward references between constants, `{` on the next line, locals that shadow fields,
duplicate `uses` entries, and `init`/`recv` used as names.

## Decision
Every program Fe0 accepts must also be accepted by the official compiler and behave the same.
Where Fe is more permissive, Fe0 keeps the stricter rule, which the subset rule allows: it
leaves fewer cases to specify. Where SPEC.md and the compiler disagree, the compiler wins and
the spec is fixed. Rules not yet confirmed by a probe are marked [V] in SPEC.md.

## Alternatives
- **Follow Fe in every permissive case:** more of the spec to write and to test, for programs
  nobody needs to write.
- **A Fe-like language with its own rules:** loses the differential oracle
  ([0002](0002-match-official-output.md), [0003](0003-own-corpus-and-generator.md)), and with it
  the main evidence that the compiler is right.

## Consequences
- Each reject test also runs `fe check`, which must reject the file too (DESIGN.md §10).
- Non-`mut` contract fields turned out to be code-backed immutables, not storage, so Fe0 v1
  requires `mut` on every field.
