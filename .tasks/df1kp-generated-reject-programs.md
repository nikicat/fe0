---
status: todo
tags: [tools, subset]
---
# Generated reject programs

## Goal
`tools/gen.py` only makes programs that both compilers must accept. It avoids every shape
that Fe0 rejects (SPEC.md §1, §3.2, §3.4, §5.2), so the random rounds never test those rules.
Each rule is checked only by the reject programs in `corpus/reject/`, which were written by
hand, a few per rule. Those probes check against Fe only the shapes we thought of. The
generics rule shows the risk: the first version of Fe0's rule rejected
`if x < lo { lo } else if x > hi { hi }`, which Fe accepts, and only a corpus program caught it.

Done means: a mode of `tools/gen.py` that writes reject programs, each with the
`// expect: CODE line:col` header and, where Fe0's rule is wider than Fe's, `// fe: accepts`.
It runs them through `embed.harness` as its `rejects`, and CI runs a fixed set of seeds.

## Decisions
- Make a reject program by mutating a generated program that is accepted, at one place, so
  that it breaks one rule. The mutation knows the rule, so it knows the code and the
  position that Fe0 must give.
- The harness already checks what is needed (`Reject` and `Reject.official_failure` in
  `tools/embed.py`): Fe0's code and position, and Fe's `fe check` verdict against the
  header.

- A peer review proposed a cheaper oracle that needs no EVM run: mutate accepted programs,
  ask `fe check` for each mutant, and report every mutant that Fe rejects but Fe0 accepts.
  Mutations: re-flow whitespace, newlines and comments; wrap subexpressions in parentheses or
  blocks; reuse item names as locals and binds; insert unreachable code. Each of these found
  a real bug by hand (Tbb99s, Tcz2ax, T929gb, Tawfan).

## Next
- List the mutations, one or more per rule:
  - **Type names (§1):** rename a local, parameter, function or constant to a type name.
  - **Generics (§3.2):** drop the parentheses that `E.may_take_generics` adds, or build
    `name < args >` with the argument kinds that Fe accepts.
  - **Record literal (§3.4):** drop the parentheses that `E.may_read_as_record` adds.
  - **Uppercase locals (§5.2):** capitalize a local.
  - **Other rules:** a local named like a constant, a chained comparison, a constant cycle.
- For a rule wider than Fe's, the mutation can't always tell whether Fe accepts the result.
  Decide whether it asks `fe check` and then writes the header, or only makes shapes whose
  verdict it knows.
