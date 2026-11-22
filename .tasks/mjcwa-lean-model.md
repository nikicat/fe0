---
status: todo
tags: [spec, lean]
---
# A Lean model of Fe0

## Goal
The Fe team wants a subset of Fe small enough to formalize in Lean (docs/PLAN.md §0). The
README section "Fe0 as a subset to formalize" says Fe0 could be that subset, and that it has no
Lean model. This task writes one.

Done, for the first milestone, means a Lean 4 model of Fe0's syntax tree, static rules and
dynamic rules, run as an interpreter over the corpus. A harness (step 4) compares the
model's outcomes with what Fe0's build and Fe's build do on an anvil node, and finds no
difference. The proofs are a second milestone.

## Decisions
- The model starts from the syntax tree of SPEC.md §3.1, not from the concrete syntax. The
  newline rule (§3.4) and the rule for `<` (§3.2) exist only to match Fe's parser, and add
  nothing to a theorem. The differential tests (DESIGN.md §10) cover the parser.
- It is tested before anything is proved. SPEC.md is prose, so running the model against the
  corpus is how a gap between the model, SPEC.md and Fe0 shows up.
- A proof that Fe0's compiler is correct is out of scope. The differential tests of DESIGN.md
  §10 cover that by testing.
- It starts after T0010, the contest submission. Until then Lean is only mentioned in the
  README, with no Lean code (docs/PLAN.md, risk 9).

## Plan
1. **Syntax.** Lean inductive types for the syntax tree of SPEC.md §3.1. `u256` is `BitVec 256`,
   `Address` is `BitVec 160`, and `bool` is `Bool`.
2. **Static rules.** Typing (SPEC.md §2 and §4). Names: the innermost declaration wins (§5.2),
   and no constant depends on itself (§5.3). Effects: a body may use only what its `uses` lists,
   and write only fields marked `mut` (§6). Each of these rules is an inductive relation, or a
   checking function with a proof that it matches the relation.
3. **Dynamic rules.** A total function from a state and a call to one outcome. It can be a
   function, not a relation, because SPEC.md §4 fixes every evaluation order.
   - The state is the storage of each contract.
   - An outcome is success with return data, storage writes and logs, or failure with revert
     data. Checked arithmetic reverts with the panic codes of §4.
   - The values of the `Ctx` methods and the result of each external call are inputs.
   - `keccak256` is an assumed injective function.
   - Gas and Fe's recursion limit are left out, as the subset rule leaves them out.
4. **Run it as a third oracle, beside Fe's build and Fe0's build.**
   - Give `fe0-cli` a flag that prints the syntax tree of a program, so that the model reads
     Fe0's parse and needs no parser of its own. Tgab15 plans similar flags for the tokens.
   - Compile the Lean model to an interpreter that reads that tree, and run each corpus
     program's call script on it.
   - Compare its outcome with `node_check.py`'s four fields: success, return or revert data,
     logs, and storage writes.
   - Fix each difference in SPEC.md, the model or Fe0. Fe's build decides which is wrong, as
     the subset rule at the top of SPEC.md says.
5. **Proofs (second milestone)**, roughly from easy to hard:
   - free functions are pure (SPEC.md §5.5);
   - type safety: a well-typed body gives a value of its type, or fails with the revert data of
     §4 and §6;
   - effect safety: a running body reads, emits and calls only through what its `uses` lists,
     and writes only fields marked `mut`;
   - the dispatcher and `init` decode their input as §6 says.

## Next
- After the submission: pick the Lean 4 version, whether `BitVec` comes from core or Mathlib,
  where the Lean code lives, and whether step 4's harness extends `node_check.py` or is a new
  tool. Then write step 1.
