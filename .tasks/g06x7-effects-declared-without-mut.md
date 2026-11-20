---
status: todo
tags: [conformance]
---
# Accept `Log` and `Call` effects declared without `mut`

## Goal
The contract's own `uses` must declare `log: mut Log` and `call: mut Call`. Without `mut`, Fe0
rejects the declaration with `P002`, in the grammar's `effect` rule (SPEC §3.1). Fe accepts the
declaration, and rejects only a body that emits through it (`8-0066`) or calls through it
(`8-0037`). This is the last ◐ row in the effects part of SPEC §10, "`Log` and `Call` declared
without `mut`". Done means Fe0 follows Fe here, or ADR 0001 records why it doesn't.

## Decisions
- ADR 0001 follows Fe where the cost is small. Following Fe for names, grants and forward
  constants cost the Checker 100 bytes (Fe 26.7.0, `-O s`).

## State
- The parser rejects the declaration in `fe0/src/parser.fe` (`P_FIELD_NOT_MUT`, the
  `self.err` at about line 550).
- Bodies may grant `log` and `call` without `mut` (`Checker.emit`, `Checker.use_call_effect`).

## Next
1. Probe Fe 26.7.0 on these cases: a declaration without `mut` that no body uses; one that a
   body emits or calls through; a grant of it in `uses`, with `mut` and without.
2. If the probes match SPEC, let the parser accept the declaration. Then the Checker should
   reject an emit or a call through a non-`mut` effect, with E018 or a new code.
3. Measure the Parser and Checker bytes, and update SPEC §3.1, §6 and §10.
