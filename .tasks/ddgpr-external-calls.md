---
status: todo
deps: [T3jcng]
tags: [spec, checker, codegen]
---
# Step 4: typed calls to other contracts

## Goal
ADR 0020. `call: mut Call` in a contract's `uses`, and the fixed expression
`a.call(M::V { … })` for a variant of a declared `msg`. It reverts with the callee's revert
data and decodes one word on success. Done means SPEC, checker, code generation, `amm.fe`
moving two real tokens, call scripts that pass one deployment's address to another, and every
phase contract under 24,576 bytes.
