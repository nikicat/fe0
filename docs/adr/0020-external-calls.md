# 20. Typed calls to other contracts

- Date: 2026-11-12
- Status: accepted; step 4 of [0016](0016-steps-toward-real-contracts.md)

## Context
A router, a pool or a vault moves tokens by calling the token contracts. Fe calls another
contract with a value of one of its `msg` types, through the `Call` effect:

```fe
msg Erc20 {
    #[selector = 0xa9059cbb]
    Transfer { to: Address, amount: u256 } -> bool,
}

// in a body whose uses names call:
let ok = token.call(Erc20::Transfer { to, amount })
```

`Address::call` sends no value and forwards all the gas. It reverts with the callee's revert
data when the callee fails, and returns the decoded result when it succeeds.

## Decision
Fe0 adds this one form:
- a contract may declare `call: mut Call` in its `uses`;
- the expression `a.call(M::V { f: e, … })`, where `a` is an `Address` and `M::V` is a variant
  of a `msg` the program declares. Its type is the variant's return type, or unit without one;
- code generation encodes the selector and the arguments as ABI words, emits `CALL` with all
  the remaining gas, copies the callee's revert data when it fails, and decodes one word when it
  succeeds.

## Alternatives
- **`try_call`, `static`, gas and value:** each is another fixed form. `try_call` returns a
  `CallOutcome`, a type Fe0 does not have. They wait until a program needs them.
- **Calls through an interface type:** Fe has none. A `msg` is the interface.

## Consequences
- A contract can now be re-entered by the contract it calls. Fe0 has no reentrancy guard in the
  language, as Fe has none. A program guards itself with a storage flag, as Solidity programs
  do.
- `amm.fe` can move two real tokens, and the corpus can hold a pool that is a real pair minus its
  LP-token transfers.
- The differential harness on a node deploys the callees too. A call script needs a way to pass
  one deployment's address to another, such as `deploy as token` and `@token` in arguments.

## Update (Nov 14)
- SPEC §6, "Calls" states the rules this work settled, and SPEC §4 the order of evaluation.
  Fe's behaviour was probed on anvil against hand-written contracts that echo their calldata or
  revert with it, and Fe0's build matched Fe's on all 33 probe calls. `corpus/calls.fe` keeps
  the probe in the corpus, against `corpus/callee.fe`.
- **The effect is found by its type.** `a.call(…)` does not name its effect, as in Fe. So
  Fe0 allows one `Call` effect per contract, and a body must grant it with `mut`. Fe is looser
  on both (SPEC §6, "Calls"), and the subset rule allows Fe0 to be stricter.
- **`ctx.address()`.** A pool asks each token for its own balance, as a Uniswap v2 pair does
  with `balanceOf(address(this))`. `corpus/token.fe` has no allowances, and Fe0's maps take one
  key, so a pool cannot pull tokens with `transferFrom`. So Fe0 also adds `ctx.address()`, the
  `ADDRESS` instruction, with the rules of `ctx.caller()`.
- `corpus/amm.fe` is now a v2-style pair of two `corpus/token.fe` deployments. A trader sends
  tokens to the pair with the token's own `Transfer`, then calls `Swap`, which pays out first
  and then checks the balances against the reserves after the fee. `Mint` and `Burn` count
  liquidity per provider, without an LP token. A `locked` flag guards every arm that calls a
  token against a token that calls back.
- **Call scripts** gain `deploy token.fe as t0 ARGS`, `@t0` as an argument and `@t0 Transfer …`
  for a call to that deployment (`tools/embed.py`). Such a program runs only on a node, where
  both builds' contracts get the same addresses (DESIGN.md §10, "On a node").
- **Size, at `-O s`:** Parser goes from 22,072 to 22,694 bytes (+622), Checker from 21,411 to
  22,294 (+883) and Back from 17,049 to 17,976 (+927). Of the parser's bytes,
  `ctx.address()` costs 52, since it shares one node constructor with `ctx.caller()`. A first
  version with its own constructor cost 412. The contracts on Arbitrum One are the build
  before this change, so a program that calls another contract compiles only after a
  redeployment.
