# 17. The caller, through a `Ctx` effect

- Date: 2026-11-12
- Status: accepted; step 1 of [0016](0016-steps-toward-real-contracts.md)

## Context
Fe0 cannot tell who calls a contract. `Address` values only come in as parameters, from
storage or as return values (SPEC.md §2). So a contract cannot check its owner, and it cannot
keep anything per caller. Fe reads the caller through the `Ctx` effect, declared at the
contract and named in each body that uses it:

```fe
pub contract Owned uses (ctx: Ctx) {
    mut owner: Address,

    init() uses (ctx, mut owner) {
        owner = ctx.caller()
    }

    recv OwnedMsg {
        SetOwner { new_owner } uses (ctx, mut owner) {
            assert!(ctx.caller() == owner, "not the owner")
            owner = new_owner
        }
    }
}
```

## Decision
Fe0 adds `Ctx` effects and the methods of `Ctx` that read one value, and nothing more general:
- a contract may declare `Ctx` effects in its `uses`, under any name and any number of them,
  written `Ctx` or `mut Ctx`. Fe accepts all of these **[✓]**. An effect is a contract field of
  type `Ctx` with no storage (DESIGN.md §5), so any name and several effects cost nothing extra;
- `init` and arms may name an effect in their `uses`, with or without `mut`;
- `ctx.m()` reads one value, in a body whose `uses` names `ctx`. `m` is any method of Fe's `Ctx`
  that takes no arguments and returns `u256` or `Address`, except `gas`, such as `caller`,
  `address` and `block_number`. SPEC §6, "The caller", lists them and gives the rules;
- the expression `Address::zero()` has type `Address`.

Method calls stay out of Fe0 in general (SPEC.md §3.3). The parser reads `ctx.m()` and
`Address::zero()` as fixed forms, and it takes any method name `m`. The checker resolves `m`
with a chain of tests, and keeps the method's instruction for code generation, which emits it
(`CALLER` for `caller`, `NUMBER` for `block_number`) and `PUSH0` for `Address::zero()`. A
program that names an effect in a free function, or calls a method of `Ctx` that Fe0 leaves
out, gets an error.

The parser matches the fixed words, such as `Ctx`, through `Text.packed`. The words are
`Spelling` constants passed as arguments. On Fe 26.7.0, which passes one-scalar constants as
values (argotorg/fe#1978, [0022](0022-move-to-26-7-0.md)), they cost nothing.

The lexer reads `::` as two `:` tokens, and the parser checks that they touch.

## Alternatives
- **General method calls:** they need method resolution, `impl` blocks and receivers, which is
  most of what [0007](0007-codegen-from-ast.md) and SPEC §3.3 kept out. The fixed forms need
  none of that.
- **Only `uses (ctx: Ctx)`, with that one name:** stricter than Fe for no saving, since an
  effect takes no storage.
- **`ctx.gas()`:** the Fe build and the Fe0 build of one program have different gas left, so
  the differential test cannot compare them.
- **`ctx.timestamp()`, `ctx.value()` and `ctx.selfbalance()`:** they return types that Fe0 does
  not have. Each waits for its type.
- **The parser matches each method name:** it made the Parser 116 bytes larger than reading any
  name and leaving the method to the checker (Fe 26.6.0, `-O s`).
- **A table of the methods instead of the chain of tests:** it makes the Checker 1,227 bytes
  larger (Fe 26.7.0, `-O s`). A constant array stores every field of every element as a
  32-byte word.
- **The fixed words as plain `u256` constants instead of `Spelling`:** the Parser is 1 byte
  larger (Fe 26.7.0, `-O s`).
- **`spells<N>` to match the words:** it takes a word of one fixed length `N`, and
  `Parser.effect` matches words of two different lengths.
- **`::` as one token:** it cost 244 bytes in the lexer (Fe 26.6.0, `-O s`).

## Consequences
- Owner checks become possible, and with step 2 ([0018](0018-storage-maps.md)), state per
  caller.
- The differential harness must send calls from several accounts (step 0 of
  [0016](0016-steps-toward-real-contracts.md)), so that a program's "not the owner" path is
  tested against Fe.
- Fe0 can make an `Address`: `Address::zero()` and the methods of `Ctx` that return an
  `Address` give one (SPEC §2).
