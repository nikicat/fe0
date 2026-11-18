---
status: todo
tags: [compiler, size, unsmell]
---
# Typed views over `Node`, and typed ids from `Checked.res`

## Goal
A `Node` (fe0/src/ast.fe) is a sum type written by hand. `kind` is the tag, and the slots `a`
to `d` hold each kind's fields, so one slot means different things for different kinds. For
example, `d` is a body, an init, a string length or a flag, and `Node.flag_set` reads the flag
for four kinds. Nothing stops a reader from calling an accessor that does not belong to the
node's kind.

`Checked.res` (fe0/src/check.fe) is the same smell on the checker's side. What it holds
depends on the node's kind. The seven accessors that read it (`declaration`, `map_field`,
`field_of`, `event_of`, `callee`, `msg_of`, `variant_of`, Nov 18) only add names: each takes
and returns a `NodeId`, so `variant_of(emit_node)` compiles and returns an event.

Done means: each kind has a typed view, and each `res` accessor takes and returns a typed id
(such as `VariantId` or `FieldId`, each wrapping a `NodeId`). Or a measurement shows they cost
too much bytecode, and the reason is written into ADR 0005.

## Decisions
- Keep the storage. ADR 0005 keeps nodes in one flat `MemVec<Node>` of fixed-size records:
  Fe has no recursive types without `unsafe`, one `NodeId` reaches any node, child lists mix
  kinds, and the arrays serialize as words for the on-chain phases (ADR 0014).
- The candidate is a view per kind over the same storage, such as `LetNode { n: Node }`, got
  from `node.as_let()` and offering only that kind's accessors. It changes no storage and no
  serialization, so it can be done one kind at a time.

## Ruled out
- A Fe `enum Node` with a payload per variant: it breaks the word layout of the arrays, and
  `Option<Label>` alone cost 919 bytes (ADR 0014). On Fe 26.6.0 an enum crosses a contract
  boundary only through a `match` per variant: `enum Tok` cost 1.8 to 2.5 KB per contract,
  and the 3-variant `BodyKind` cost Back 443 bytes (Nov 17). Revisit when Fe has a cast
  between an enum and its index (argotorg/fe#2020).
- One type and one array per kind: a `NodeId` would have to carry its kind, and child lists
  mix kinds. It amounts to rewriting the parser, the checker and code generation.

## State
- `LetNode` (fe0/src/ast.fe), from `node.as_let()`, is the first view. It replaced
  `Node.is_var` and cost 0 bytes in Parser, Checker and Back (Fe 26.6.0, -O s, Nov 15).
- `as_let` does not check the kind. A check would cost bytes in every phase.

## Next
0. Typed ids for the `res` accessors, one kind at a time, measured like the views. Fe 26.6.0
   copies a function once per struct constant passed to it (task Ts3ty7), so a wrapper type
   may not be free; it is free if it is only ever built from a variable.
1. A view for each kind whose slot `d` means a flag: USE (`is_mut`), the positional bind
   (`is_positional`), BOOL (`is_true`) and an event's FIELD (`is_indexed`). Then drop
   `Node.flag_set`.
2. Then the kinds whose `d` is a body, an init, a key or a variant. Measure each step with
   the size report of `tools/chain_check.py`, since a later view may not be free.
