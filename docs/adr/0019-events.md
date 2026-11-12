# 19. Events

- Date: 2026-11-12
- Status: accepted; step 3 of [0016](0016-steps-toward-real-contracts.md)

## Context
Wallets, explorers and indexers follow a token through its `Transfer` and `Approval` events.
Fe declares an event as a struct with `#[event]`, marks the indexed fields, and emits it
through the `Log` effect:

```fe
#[event]
struct TransferEvent {
    #[indexed]
    from: Address,
    #[indexed]
    to: Address,
    value: u256,
}

// in a body whose uses names log:
log.emit(TransferEvent { from, to, value: amount })
```

Fe0 has no structs, no struct literals and no `Log` effect.

## Decision
Fe0 adds events and nothing else of structs:
- a top-level `#[event] struct` whose fields are `u256`, `bool` or `Address`, each optionally
  `#[indexed]`, with at most three indexed fields;
- a contract may declare `log: mut Log` in its `uses`, beside `ctx: Ctx`;
- the statement `log.emit(E { f: e, … })`, a fixed form like `ctx.caller()`
  ([0017](0017-caller.md)). The literal names every field of `E` once, and the checker types
  each value.

Code generation emits `LOG1` to `LOG4`. Topic 0 is the keccak of the event's signature, as Fe
computes it. The compiler computes it with `core::keccak`, which lowers natively on Fe 26.6.0
([0015](0015-move-to-26-6-0.md)). The other topics are the indexed fields, and the data is the
other fields as ABI words.

## Alternatives
- **Structs in general:** field access, struct values in locals and parameters, and memory
  layout. Events need none of that, since the literal is used once, in place.

## Consequences
- With steps 1 and 2, a token emits standard `Transfer` events.
- The harness on a node compares the logs of each call (step 0 of
  [0016](0016-steps-toward-real-contracts.md)), since logs are not visible inside `fe test`.
- The event signature depends on Fe's spelling of the types (`address`, `uint256`, `bool`). A
  corpus probe pins topic 0 against Fe.
