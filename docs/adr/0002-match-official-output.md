# 2. Match the official compiler's storage, ABI and revert data exactly

- Date: 2026-10-28 (pre-window)
- Status: accepted

## Context
The subset rule ([0001](0001-strict-subset.md)) says Fe0's output behaves the same as the
official compiler's. The differential harness can only check that if "the same" means identical
bytes. Probes of the official compiler (`spike-layout/`, from `fe test --trace-evm` and revert
payloads) give:
- **Storage:** fields take slots in declaration order from 0, and narrow fields share a slot
  (#1826). `true` is stored as 1. SPEC §6 has the rule.
- **Return data:** standard ABI, one 32-byte word per value.
- **Panics:** `Panic(0x11)` for overflow and underflow, `Panic(0x12)` for division by zero,
  `Panic(0x01)` for `assert!(false)`, each `0x4e487b71` followed by the code word.
- **`assert!(c, "m")`:** Solidity `Error(string)`, `0x08c379a0` plus the ABI string.
- **Unknown selector:** revert with empty data.

## Decision
Fe0 emits exactly these layouts and payloads, and the dispatcher mirrors the official one
(DESIGN.md §6.4). The harness compares success flags and returndata byte for byte, revert
data included.

## Alternatives
- **Compare only success or failure:** easier to pass, but it misses wrong panic codes and
  wrong storage slots, which are exactly the bugs a code generator has.

## Consequences
- These are Solidity's conventions, so Fe0's contracts work with existing tooling too.
- `assert!` messages are capped at 31 bytes so that `Error(string)` stays one data word
  (SPEC.md §1).
