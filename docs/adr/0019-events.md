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

## Update (Nov 12)
- SPEC §6, "Events" states the rules this work settled: topic 0, the order of topics and data,
  and what Fe accepts and Fe0 rejects. SPEC §4 states the order in which the values of the
  literal are evaluated. Both name their probes. On a node, Fe0 matches Fe on
  `corpus/events.fe` at `-O 1` and `-O s`.
- **Hashing.** `core::keccak` takes an array of a size fixed at compile time, and a signature's
  length is known only when Fe0 runs. So the checker builds the signature in a `MemVec<u8>`
  and hashes it with `std::evm::crypto::keccak256`. On the EVM that is the `KECCAK256`
  instruction, and natively Fe's software keccak.
- `corpus/token.fe` emits `Transfer` on deployment, on each transfer and on each mint.
- **Size, at `-O s`:** LexProbe goes from 7,141 to 7,139 bytes, since `struct` became a keyword
  and left the reserved list. ParseProbe goes from 26,328 to 27,915 bytes (+1,587), CheckProbe
  from 42,325 to 45,418 (+3,093) and CompileProbe from 56,475 to 60,071 (+3,596). Of the
  parser's bytes, event items cost 606 and `emit` 571. Inlining `emit` into `effect_call` was
  measured at 29 more bytes, so `emit` stays its own function. The attribute helpers that the
  selector now shares saved 179, and shared helpers for bracketed lists saved 279 more.
- **The checker owns the log's layout.** It records each event's topic 0 and number of data
  words in an `EventLog` table, and each field's word of the log data. Code generation reads
  only these, so the `Back` contract needs neither the source nor keccak (DESIGN.md §8). The
  table costs about 280 bytes in CheckProbe and 400 in CompileProbe.
