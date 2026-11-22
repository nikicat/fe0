# 27. Phase contracts trust their input

- Date: 2026-11-14
- Status: accepted

## Context
Each phase of the on-chain compiler is its own contract ([0014](0014-contract-per-phase.md)),
and each phase contract must fit in 24,576 bytes. Compiler, the intended caller, gives each
phase the previous phase's output as `uint256[]` words in the format of `fe0/src/wire.fe`
(DESIGN.md §8). Anyone can also call a phase contract directly.

## Decision
A phase contract trusts its input and decodes it without checks. A direct caller that sends
malformed words gets a revert or a wrong result, and only for itself: the phases keep no
state, so the call changes nothing on chain.

## Alternatives
- **Check the words on decode:** checks would cost bytes in every phase contract.

## Consequences
- A reader in `fe0/src/wire.fe` trusts its words and checks nothing.
- For the same reason, a view of a node does not check the node's kind
  ([0005](0005-arena-ast.md)).
