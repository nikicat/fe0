# 1. Fe0 is a strict subset of Fe, stricter where Fe is permissive

- Date: 2026-10-28 (pre-window)
- Status: accepted

## Context
The Fe team wants a Fe subset small enough to formalize in Lean, and two judges are Fe core
developers. A subset that drifts from Fe, or has corners its spec doesn't pin down, would not
survive their review. Probes against the official compiler (`spike-conform/`) show places
where Fe is more permissive than a small spec would be, such as uppercase locals and `init` or
`recv` used as names. Following Fe in such a place means more spec, more tests and, since Fe0
runs on chain, more bytes in the phase contracts ([0014](0014-contract-per-phase.md)). Not
following it means that Fe0 rejects programs that Fe accepts.

## Decision
Every program Fe0 accepts must also be accepted by the official compiler and behave the same.
Within the subset, Fe0 also accepts every program Fe accepts when following Fe is cheap. The
names, grants, constants and effect declarations below show what cheap is. The uppercase locals
below show what is too costly, and there Fe0 keeps a stricter rule, which the subset rule allows.
Where SPEC.md and the compiler disagree, the compiler wins and the spec is fixed. Rules not yet
confirmed by a probe are marked [V] in SPEC.md.

SPEC.md §10 lists every stricter rule. Among them:
- **Uppercase locals are rejected (`N017`).** Matching Fe's narrower rule (SPEC.md §5.2) needs
  a table in the Checker of the names that Fe reads as patterns. That table made the Checker
  contract 891 bytes larger (Fe 26.6.0, `-O s`).
  Uppercase parameters are accepted, as in Fe.

In the cases below, a stricter rule would reject Fe programs, and following Fe costs the
Checker contract 100 bytes for the first three together and 133 bytes for the fourth (Fe 26.7.0,
`-O s`). So Fe0 follows Fe:
- **A local or a parameter may take the name of a field or an item, and hides it.** Fe0
  rejects only the names that Fe rejects too (SPEC §5.2).
- **A body may grant a `Log` or `Call` effect without `mut`** (SPEC §6).
- **A constant may refer to a later constant** (SPEC §5.3).
- **A contract may declare a `Log` or `Call` effect without `mut`.** Fe0 rejects only an emit
  or a call through it (SPEC §6).

In two more cases, following Fe made the Lexer contract 164 bytes smaller and the Parser
contract 36 bytes larger (Fe 26.7.0, `-O s`):
- **A width that Fe lacks, such as `u7` or `u24`, is a name** (SPEC §1).
- **`init`, `recv`, `assert` and `with` are names** (SPEC §1).

Where Fe is just as strict, so is Fe0. A field listed twice in a `uses` clause and an effect
name declared twice are both rejected (`N001`), as Fe 26.7.0 rejects them (`3-0093`,
argotorg/fe#1987). A `Ctx` effect may be written `mut Ctx`, as in Fe.

## Alternatives
- **Follow Fe in every permissive case:** more of the spec to write and to test, and more
  bytes on chain, for programs nobody needs to write.
- **Keep a stricter rule even where following Fe is free:** each such rule rejects Fe programs
  for no gain.
- **Keep the stricter name, grant, constant and effect declaration rules of the first four
  cases above:** a name would always mean one declaration, and only `mut` would grant or
  declare a change. But each rule rejects Fe programs. Following Fe in those four cases costs
  the Checker only 233 bytes.
- **A Fe-like language with its own rules:** loses the differential oracle
  ([0002](0002-match-official-output.md), [0003](0003-own-corpus-and-generator.md)), and with it
  the main evidence that the compiler is right.

## Consequences
- Each reject test also runs `fe check`, which must reject the file too (DESIGN.md §10).
- In Fe a contract field without `mut` is a code-backed immutable, not storage, so Fe0 v1
  requires `mut` on every field.
- Rejecting a field listed twice in `uses` costs the Checker contract 58 bytes (Fe 26.7.0,
  `-O s`).
