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
