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

SPEC §6, "Events", gives the rules: topic 0, the order of topics and data, and what Fe accepts
and Fe0 rejects. SPEC §4 gives the order in which the values of the literal are evaluated.

Code generation emits `LOG1` to `LOG4`. Topic 0 is the keccak of the event's signature, as Fe
computes it. The other topics are the indexed fields, and the data is the other fields as ABI
words.

The checker owns the log's layout. It builds each event's signature in a `MemVec<u8>` and
hashes it with `std::evm::crypto::keccak256`. On the EVM that is the `KECCAK256` instruction,
and natively Fe's software keccak. It records each event's topic 0 and number of data words in
an `EventLog` table, and each field's word of the log data. Code generation reads only these,
so the `Back` contract needs neither the source nor keccak (DESIGN.md §8).

## Alternatives
- **Structs in general:** field access, struct values in locals and parameters, and memory
  layout. Events need none of that, since the literal is used once, in place.
- **Hash the signature with `core::keccak`:** it takes an array of a size fixed at compile
  time, and a signature's length is known only when Fe0 runs.
- **Compute topic 0 in code generation:** the `Back` contract would need the source and keccak.

## Consequences
- With steps 1 and 2, a token emits standard `Transfer` events. `corpus/token.fe` emits
  `Transfer` on deployment, on each transfer and on each mint.
- The harness on a node compares the logs of each call (step 0 of
  [0016](0016-steps-toward-real-contracts.md)), since logs are not visible inside `fe test`.
  On a node, Fe0 matches Fe on `corpus/events.fe` at `-O 1` and `-O s`.
- The event signature depends on Fe's spelling of the types (`address`, `uint256`, `bool`).
  `corpus/events.fe` pins topic 0 against Fe.
