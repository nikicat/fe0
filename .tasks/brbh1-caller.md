---
status: todo
deps: [Tf435j]
tags: [spec, checker, codegen]
---
# Step 1: the caller, through a `Ctx` effect

## Goal
ADR 0017. A contract may declare `uses (ctx: Ctx)`, bodies may name `ctx`, and the fixed
forms `ctx.caller()` and `Address::zero()` have type `Address` (`CALLER`, `PUSH0`). Done means
SPEC, checker, code generation, an owner-checking corpus program with calls from two senders,
reject programs, and every phase contract under 24,576 bytes.
