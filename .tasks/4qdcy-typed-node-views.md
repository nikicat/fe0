---
status: todo
tags: [compiler, size, unsmell]
---
# Typed views over `Node`

## Goal
A `Node` (fe0/src/ast.fe) is a sum type written by hand. `kind` is the tag, and the slots `a`
to `d` hold each kind's fields, so one slot means different things for different kinds. For
example, `d` is a body, an init, a string length or a flag, and `Node.flag_set` reads the flag
for four kinds. Nothing stops a reader from calling an accessor that does not belong to the
node's kind. Done means: either each kind has a typed view, or a measurement shows the views
cost too much bytecode and the reason is written into ADR 0005.

## Decisions
- Keep the storage. ADR 0005 keeps nodes in one flat `MemVec<Node>` of fixed-size records:
  Fe has no recursive types without `unsafe`, one `NodeId` reaches any node, child lists mix
  kinds, and the arrays serialize as words for the on-chain phases (ADR 0014).
- The candidate is a view per kind over the same storage, such as `LetNode { n: Node }`, got
  from `node.as_let()` and offering only that kind's accessors. It changes no storage and no
  serialization, so it can be done one kind at a time.

## Ruled out
- A Fe `enum Node` with a payload per variant: it breaks the word layout of the arrays, and
  `Option<Label>` alone cost 919 bytes (ADR 0014). ParseProbe has about 340 bytes left.
- One type and one array per kind: a `NodeId` would have to carry its kind, and child lists
  mix kinds. It amounts to rewriting the parser, the checker and code generation.

## Next
1. Try a view for one kind, `LET` with its `var` flag, and measure the four probes of
   `spike-sizes/` at `-O s` before and after.
2. Small wrappers and accessors can cost bytecode under argotorg/fe#1964 (WORKAROUNDS.md
   says which shapes, and what #1978 fixed on Fe's master). Measure the views again on the
   first release that has #1978, before deciding against them.

Found by the /unsmell run of 2026-11-12 (finding b2-4), while reviewing `Node.flag_set`.
