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

## Update (Nov 17)
The decision is narrower now. Where Fe is more permissive and following it costs nothing in the
size of the on-chain phase contracts, Fe0 follows Fe. Each stricter rule is a place where a Fe
program does not compile with Fe0, and SPEC.md §10 lists them.

- **Now as in Fe.** Fe0 accepts a field listed twice in the `uses` of `init` or of an arm, and
  the last entry decides `mut`. A `Ctx` effect may be written `mut Ctx`. A parameter may start
  with an uppercase letter.
- **Uppercase locals stay rejected (`N017`).** Fe rejects a local only when it names a struct,
  an enum or a variant of Fe's prelude. Matching that rule needs a table of those names in the
  Checker. The table made the Checker contract 891 bytes larger, from 22,205 to 23,096 bytes
  (Fe 26.6.0, `-O s`, Nov 17).
- **The same effect name declared twice stays rejected (`N001`).** Fe accepts it, even for two
  kinds of effect under one name, such as `a: Ctx, a: mut Log`. Fe0 would need Checker bytes
  to resolve such a name, for a program nobody writes.
