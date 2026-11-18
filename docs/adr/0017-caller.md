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

## Update (Nov 12)
- **Any name, any number of effects.** Fe accepts `uses (c: Ctx)` and two effects of type `Ctx`
  **[✓]**. An effect became a contract field of type `Ctx` with no storage (DESIGN.md §5). So
  any name and several effects cost nothing extra, and Fe0 accepts them too.
- **`uses (mut ctx)`** is accepted, as Fe accepts it **[✓]**.
- SPEC §6, "The caller", gives the rules for `Ctx` effects.
- **Size, at `-O s`:** The whole caller feature leaves LexProbe at 7,141 bytes. It takes
  ParseProbe from 24,213 to 25,448 bytes (+1,235), CheckProbe from 39,684 to 41,074 (+1,390)
  and CompileProbe from 53,151 to 54,641 (+1,490).
- Fe0 matches the fixed words through `Text.packed` instead of `spells<N>`. The words are
  `Spelling` constants passed as arguments, which costs about 470 bytes per phase. This is the
  constant-argument shape of argotorg/fe#1964 in [WORKAROUNDS.md](../WORKAROUNDS.md). The cost
  is accepted for now. Measure it again on a release that has #1978.
- The parser reads the effects with the comma-list loop it shares with other lists, which
  saved 310 bytes.
- Lexing `::` as one token cost 244 bytes in the lexer. So the lexer keeps two `:` tokens, and
  the parser checks that they touch.

## Update (Nov 17)
- **Every `Ctx` method without arguments that returns `u256` or `Address`, except `gas`.** Fe0
  adds all such methods of Fe's `Ctx` beside `caller` and `address` (SPEC §6, "The caller").
  `gas` stays out, because the Fe build and the Fe0 build of one program have different gas
  left, so the differential test cannot compare them.
- **The parser reads any `ctx.m()`, and the checker resolves `m`.** The parser no longer
  matches `caller` and `address`, which made it 116 bytes smaller (22,578). The checker looks
  `m` up in a chain of tests and keeps the instruction for code generation. The Checker grew by
  442 bytes (22,535), and Back shrank by 7 (Fe 26.6.0, `-O s`).
- A table of the methods instead of the chain made the Checker 1,605 bytes larger: a constant
  array stores every field of every element as a 32-byte word.
