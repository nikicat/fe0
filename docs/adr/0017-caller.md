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
Fe0 adds exactly this shape, and nothing more general:
- a contract may declare `uses (ctx: Ctx)`, with that one effect and that name;
- `init` and arms may name `ctx` in their `uses`;
- the expression `ctx.caller()` has type `Address`, in a body whose `uses` names `ctx`;
- the expression `Address::zero()` has type `Address`.

Method calls stay out of Fe0 in general (SPEC.md §3.3). `ctx.caller()` and `Address::zero()`
are fixed forms that the parser reads as whole expressions, not a call of a method or of a path.
Code generation emits `CALLER` and `PUSH0`. A program that names `ctx` in a free function, or
calls another method of `ctx`, gets an error.

## Alternatives
- **General method calls:** they need method resolution, `impl` blocks and receivers, which is
  most of what [0007](0007-codegen-from-ast.md) and SPEC §3.3 kept out. One fixed form costs a
  few hundred bytes of parser and checker.
- **`ctx.value()` and `ctx.block_number()` as well:** arms are non-payable, so the value is
  always 0, and nothing in the planned corpus needs the block yet. Each can be added later in
  the same way. `ctx.timestamp()` returns Fe's `Timestamp` type, so it waits for a type of its own.

## Consequences
- Owner checks become possible, and with step 2 ([0018](0018-storage-maps.md)), state per
  caller.
- The differential harness must send calls from several accounts (step 0 of
  [0016](0016-steps-toward-real-contracts.md)), so that a program's "not the owner" path is
  tested against Fe.
- SPEC §2's note that Fe0 cannot construct an `Address` changes: `ctx.caller()` and
  `Address::zero()` construct one.
