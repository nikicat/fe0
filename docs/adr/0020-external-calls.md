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
- a contract may declare one `Call` effect in its `uses`, such as `call: mut Call`, and a body
  grants it in its own `uses`. `a.call(…)` does not name its effect, as in Fe, so the effect is
  found by its type. Fe accepts a second `Call` effect in some programs (SPEC §6, "Calls"),
  and the subset rule allows Fe0 to be stricter;
- the expression `a.call(M::V { f: e, … })`, where `a` is an `Address` and `M::V` is a variant
  of a `msg` the program declares. Its type is the variant's return type, or unit without one;
- code generation encodes the selector and the arguments as ABI words, emits `CALL` with all
  the remaining gas, copies the callee's revert data when it fails, and decodes one word when it
  succeeds.

SPEC §6, "Calls", gives the rules, and SPEC §4 the order of evaluation.

Fe0 also adds `ctx.address()`, the `ADDRESS` instruction, with the rules of `ctx.caller()`
([0017](0017-caller.md)). A pool asks each token for its own balance, as a Uniswap v2 pair does
with `balanceOf(address(this))`. It cannot pull tokens with `transferFrom`, because
`corpus/token.fe` has no allowances and Fe0's maps take one key.

## Alternatives
- **`try_call`, `static`, gas and value:** each is another fixed form. `try_call` returns a
  `CallOutcome`, a type Fe0 does not have. They wait until a program needs them.
- **Calls through an interface type:** Fe has none. A `msg` is the interface.

## Consequences
- A contract can be re-entered by the contract it calls. Fe0 has no reentrancy guard in the
  language, as Fe has none. A program guards itself with a storage flag, as Solidity programs
  do.
- `corpus/amm.fe` is a v2-style pair of two `corpus/token.fe` deployments. A trader sends tokens
  to the pair with the token's own `Transfer`, then calls `Swap`, which pays out first and then
  checks the balances against the reserves after the fee. `Mint` and `Burn` count liquidity per
  provider, without an LP token. A `locked` flag guards every arm that calls a token against a
  token that calls back.
- Fe's behaviour is probed on anvil against contracts that echo their calldata or revert with
  it. `corpus/calls.fe` keeps the probe in the corpus, against `corpus/callee.fe`.
- The differential harness on a node deploys the callees too. Call scripts have
  `deploy token.fe as t0 ARGS`, `@t0` as an argument and `@t0 Transfer …` for a call to that
  deployment (`tools/embed.py`). Such a program runs only on a node, where both builds'
  contracts get the same addresses (DESIGN.md §10, "On a node").
