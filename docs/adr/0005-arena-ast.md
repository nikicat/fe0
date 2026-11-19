# 5. The AST is an index-based arena

- Date: 2026-10-28 (pre-window)
- Status: accepted

## Context
Fe has recursive types only through raw `*T`, which needs `unsafe`. A tree of boxed nodes is
therefore not an option. `MemVec` growth is linear on the EVM (`spike-limits/`): 851–902 gas
per item across three interleaved vectors on Fe 26.5.x, so about 1M gas for the AST of a 2 KB
program.

## Decision
Nodes live in flat `MemVec`s and refer to each other by index, with index 0 meaning "none".
A child list is a length-prefixed run in one array. Check results go into side tables indexed
by node, and the AST is never mutated after parsing. `fe0/src/ast.fe` declares the layout.

## Alternatives
- **`unsafe` pointers:** possible, but unsafe code in a compiler meant to be formalized is the
  wrong signal, and it buys nothing for programs of a few KB.
- **An `enum Node` with a payload per variant:** it breaks the word layout of the arrays, and
  an enum that crosses a contract boundary costs bytecode in every phase contract
  ([0014](0014-contract-per-phase.md)).
- **One type and one array per kind:** a node id would have to carry its kind, and child lists
  mix kinds. It amounts to rewriting the parser, the checker and code generation.

## Consequences
- The arrays serialize trivially as words, which the on-chain split needs
  ([0014](0014-contract-per-phase.md)).
- What each slot of a node holds is a convention, not a type. Named constructors and
  accessors keep the readers honest. An accessor on `Node` means the same for every kind that
  has it. A kind whose slot `d` holds something other than a body (a flag, an init, a key, a
  variant or a length) is read through its view, such as `as_let()`. A view may also offer
  other accessors of its kind, such as `recvs()` and `msg_name()`. A view wraps the node and
  offers only that kind's accessors.
- A view does not check the node's kind, because a check would cost bytes in every phase
  contract. The views cost no bytecode (Fe 26.7.0, `-O s`).
- The side tables of `Checked` hold node ids, and their readers return typed ids such as
  `Id<Field>` or `Id<Event>`. So code generation cannot read a field as an event.
