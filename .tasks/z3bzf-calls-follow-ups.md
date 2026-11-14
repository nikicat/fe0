---
status: todo
tags: [unsmell, checker, codegen, tools]
---
# Follow-ups from the unsmell run on typed calls (Nov 14)

## Goal
Smells that the unsmell run of Nov 14 (.git/unsmell/20261114-210144) found in the typed-calls
work (Tddgpr) and left for later.

## Next
- **fe0/src/check.fe, `recv`, `emit` and `msg_call`:** each looks up an item and checks its
  kind. The codes differ: an unknown msg is `N_NOT_A_MSG` in `recv` and `N_UNKNOWN_NAME` in a
  call. A shared lookup needs a decision on the codes, and a size measurement of Checker.
- **fe0/src/codegen.fe, `msg_call`:** about 50 lines in five sections, and only the first and
  last call named helpers. Split out the CALL and the decoding of the return word if Back does
  not grow.
- **tools/fegen.py, `Case.to`:** every deployment case carries a `to` that only a call uses.
  Options: separate deployment and call case types, or keep `to` only on calls.
- **tools/node.py:** `Node.create`, `Node.call` and `Node.code_gas` all take `book`, which
  `Session` already holds. Move them onto `Session`.
- **tools/embed.py, `parse_calls`:** four roles inline (the names an entry may use, the
  unknown-name check, the callee bookkeeping and the sorting of entries). Split them.
