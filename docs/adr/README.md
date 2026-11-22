# Architecture decision records

One file per decision that had a real alternative: its context, what was decided, what was
ruled out and what follows from it. A record states its decision as it stands now. When the
decision changes, the record is updated to match. When a decision is replaced by another, its
record is marked superseded and links to its successor.

[DESIGN.md](../DESIGN.md) describes the compiler as it is now and links here for the
reasons. Decisions dated before Nov 3 were made before the build window (pre-existing work).

To add one, copy the shape of an existing record and take the next number. When a task in
`.tasks/` closes, each of its decisions that outlives the code moves here in the same commit.

| # | Decision | Date | Status |
|---|---|---|---|
| [0001](0001-strict-subset.md) | Fe0 is a strict subset of Fe, stricter where Fe is permissive | Oct 28 | accepted |
| [0002](0002-match-official-output.md) | Match the official compiler's storage, ABI and revert data exactly | Oct 28 | accepted |
| [0003](0003-own-corpus-and-generator.md) | Write our own corpus and a random program generator | Oct 28 | accepted |
| [0004](0004-literal-selectors-first.md) | Literal selectors first; `sol()` through a `Hasher` effect later | Oct 28 | accepted; `Hasher` part superseded by 0015 |
| [0005](0005-arena-ast.md) | The AST is an index-based arena | Oct 28 | accepted |
| [0006](0006-no-error-recovery.md) | No error recovery: the first error ends the compile | Oct 28 | accepted |
| [0007](0007-codegen-from-ast.md) | Generate EVM code straight from the AST, with frames in memory | Oct 28 | accepted |
| [0008](0008-front-back-split.md) | Split the on-chain compiler into Front, Back and Compiler | Oct 28 | superseded by 0014 |
| [0009](0009-freeze-on-26-5-1.md) | Freeze the toolchain on Fe 26.5.1 | Nov 3 | superseded by 0015 |
| [0010](0010-source-effect.md) | The compiler reads its input through its own `Source` effect | Nov 4 | accepted |
| [0011](0011-error-field-not-result.md) | The lexer, the parser and the checker report errors in an `err` field, not a `Result` | Nov 4 | accepted |
| [0012](0012-max-depth.md) | The parser caps nesting at `MAX_DEPTH` = 20 | Nov 4 | accepted |
| [0013](0013-no-var-node-kind.md) | No separate node kind for `var` | Nov 4 | accepted |
| [0014](0014-contract-per-phase.md) | One contract per compiler phase | Nov 4 | accepted |
| [0015](0015-move-to-26-6-0.md) | Move to Fe 26.6.0 | Nov 11 | accepted; version superseded by 0022 |
| [0016](0016-steps-toward-real-contracts.md) | Grow Fe0 toward real contracts in steps | Nov 12 | accepted |
| [0017](0017-caller.md) | Step 1: the caller, through a `Ctx` effect | Nov 12 | accepted |
| [0018](0018-storage-maps.md) | Step 2: `StorageMap` fields | Nov 12 | accepted |
| [0019](0019-events.md) | Step 3: events | Nov 12 | accepted |
| [0020](0020-external-calls.md) | Step 4: typed calls to other contracts | Nov 12 | accepted |
| [0021](0021-frames-gas-and-depth.md) | Keep frames in memory for now; reduce their cost in steps | Nov 12 | accepted |
| [0022](0022-move-to-26-7-0.md) | Move to Fe 26.7.0 | Nov 19 | accepted |
| [0023](0023-frame-pointer-on-the-stack.md) | Keep a function's frame pointer on the stack | Nov 22 | accepted |
| [0024](0024-newline-span-carries-comment-line.md) | A newline token's span carries the last plain comment line | Nov 20 | accepted |
| [0025](0025-constants-in-passes.md) | Constants are evaluated in passes, not on first use | Nov 20 | accepted |
| [0026](0026-two-byte-jump-labels.md) | Jumps always push 2-byte labels, assembled in one pass | Oct 28 | accepted |
| [0027](0027-phase-contracts-trust-input.md) | Phase contracts trust their input | Nov 14 | accepted |
| [0028](0028-one-transaction-deploy.md) | Deploy the five contracts in one transaction through Multicall3 and CreateX | Nov 22 | accepted |
| [0029](0029-levels-not-in-ci.md) | CI does not run `node_check.py --levels` | Nov 22 | accepted |
| [0030](0030-mutations-on-text.md) | Mutations rewrite the finished program text | Nov 21 | accepted |
| [0031](0031-deployment-registry.md) | A registry of programs deployed through any Compiler | Nov 22 | proposed |
| [0032](0032-playground-architecture.md) | The playground is a TypeScript app in layers, built with Vite | Nov 22 | proposed |
