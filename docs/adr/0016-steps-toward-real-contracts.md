# 16. Grow Fe0 toward real contracts in steps

- Date: 2026-11-12
- Status: accepted

## Context
Fe0 has three types, storage fields, messages and free functions. That covers contracts that
compute over a few storage values for anyone who calls, such as an interest-rate model. It
does not cover what almost every deployed contract needs:
- the caller, for access control and per-user state;
- per-account storage, for balances and allowances;
- events, which wallets and indexers read;
- calls to other contracts, for routers and pools that move tokens.

An ERC20 token needs the first three. A pool also needs the fourth. Measurements on Nov 12
(`tools/gas_compare.py`, task Tsm5t2) show that Fe0's output costs about as much as Fe's for
storage-bound contracts (1.01 for a token, 1.07 for a pool's swap). So gas does not stop Fe0
from being used for such contracts. Only the missing features do.

## Decision
Fe0 grows in steps. Each step is one record, one task, and a complete piece of the language: its
SPEC section, its checker rules and diagnostics, its code generation, corpus programs with call
scripts, reject programs, and the differential harness. A step is done only when all of that
passes and every phase contract is still under 24,576 bytes ([0014](0014-contract-per-phase.md)).
The submission (T0010) includes the steps that are done by Nov 24, and describes the rest as
the plan.

The steps, in order. Each one unlocks something on its own:

| Step | Record | Adds | Unlocks |
|---|---|---|---|
| 0 | this record | a differential harness on a node, with several senders and logs | testing steps 1, 3 and 4 |
| 1 | [0017](0017-caller.md) | the caller, through a `Ctx` effect | owner checks, per-caller logic |
| 2 | [0018](0018-storage-maps.md) | `StorageMap` fields | balances, registries, votes per account |
| 3 | [0019](0019-events.md) | events | a standard ERC20 token, with steps 1 and 2 |
| 4 | [0020](0020-external-calls.md) | typed calls to other contracts | routers, and pools that move tokens |
| 5 | Tbzc0q | sized and signed integers | packed storage, signed math |

**Step 0.** The harness of DESIGN.md §10 runs inside `fe test`. There, every call comes from
the test contract, so a program cannot be called by two different senders, and logs are not
visible. Steps 1, 3 and 4 need both. So step 0 extends `tools/gas_compare.py`, which already
deploys Fe's and Fe0's builds on anvil and sends a call script, into a second differential
harness. A call script line gains `from=N`, the sender's account index. For each call, the
harness compares the success flag, the return data, the logs and the storage slots the call
wrote, between the two builds.

## Alternatives
- **One large step to ERC20:** nothing is usable until all of it works, and a step that is
  late leaves the submission with nothing new.
- **Features in another order:** events first would add something no corpus program can test
  without a caller or maps. Maps without a caller give per-key storage that anyone can write.

## Consequences
- Each step costs bytes in the parser, checker and code generation contracts. ParseProbe was
  24,706 bytes on Nov 11 with the lexer inside. The deployed Parser takes tokens, so it has
  more room, but a step that does not fit must first shrink something (Tbhv52 is one
  candidate).
- SPEC.md §3.3, the list of what Fe0 leaves out, shrinks with each step.
- [0002](0002-match-official-output.md) still holds: storage layout, ABI and revert data match
  Fe's exactly. For maps and events, that includes Fe's slot hashing and its log topics.
