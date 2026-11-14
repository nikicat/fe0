---
status: doing
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

## Decisions
- `a` is a name (local, parameter, bind or field) of type `Address`. Fe evaluates it first,
  then the values in the order written. They are encoded in field order.
- The checker finds the contract's one `Call` effect by type. A second `Call` effect is `N001`
  (Fe accepts two when a body grants only one). A body that calls needs `mut call` in `uses`:
  `E116` without it, `E018` without `mut` (Fe accepts `uses (call)`).
- Code generation: selector in the low bytes of the first word past the frame, values after
  it, `CALL` with `GAS`, no value, no return buffer. Failure: revert with the return data
  (stub REVERT_RETURNDATA). Success with a value: fewer than 32 bytes of return data reverts
  empty, then the first word is checked as an arm checks calldata. Extra bytes are ignored.
  A unit variant ignores the return data.
- Probed Nov 14 against Fe 26.6.0 with echo contracts on anvil (33 calls): Fe0's build matched
  Fe's on all of them.

- `ctx.address()` added (user's choice, Nov 14), so `amm.fe` is a v2-style pair that reads
  `balanceOf(ctx.address())`. Ruled out: `transferFrom` (Fe0 maps take one key, so no
  allowances), and an ERC-1363 callback (not how v2 works).
- Call scripts: `deploy token.fe as t0`, `@t0` arguments, `@t0 Transfer …` calls, `@this`.
  Such programs run only on a node. Each build runs the script from one anvil snapshot, so
  addresses match between builds (a renamer of address words could not fix map slots hashed
  from an address).

## State
All implemented: SPEC §4/§6, DESIGN §5/§6/§10, ADR 0020 update, 23 reject programs, checker
and parser tests, `corpus/calls.fe` + `corpus/callee.fe`, `corpus/amm.fe` as a pair of two
`corpus/token.fe`. Passing: fe test 61/61, embed 50 + 152 rejects, node_check 77/77 at -O 1
(amm, calls, callee, token, events also at -O s), cli_check 77/77 + 152/152. Sizes at -O s:
Parser 22,694, Checker 22,294, Back 17,976.

## Next
chain_check (amm's compile gas), then commit. The Arbitrum One deployment predates calls:
redeploy before the submission (T0010).
