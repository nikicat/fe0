# 30. Mutations rewrite the finished program text

- Date: 2026-11-21
- Status: accepted

## Context
`tools/gen.py` makes only programs that both compilers accept, so its programs never test the
rules by which Fe0 rejects a program. `tools/mutate.py` changes accepted programs, the corpus
programs and the programs that gen.py makes, and checks that both compilers accept or reject
each mutant alike (DESIGN.md §11a). Each mutation has a name, such as `paren`, which wraps a
word in parentheses.

## Decision
Mutations work on the finished program text, not inside gen.py. A mutation finds its place
with one tokenizer, `tools/fetokens.py`, which every tool that rewrites programs as text
uses.

## Alternatives
- **Mutate inside gen.py:** the mutations would not apply to the corpus, and each new mutation
  would change gen.py.

## Consequences
- The same mutations apply to the corpus and to generated programs, and a new mutation needs
  no change to gen.py.
- `paren` wraps only integer literals, `true`, `false` and the names that the program
  declares. Another keyword or a type name in parentheses would make an invalid program. In a
  program that both compilers accept, a declared name is never a keyword or a type name, so
  the tool needs no copy of SPEC.md §1's word lists.
