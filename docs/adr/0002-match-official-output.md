# 2. Match the official compiler's storage, ABI and revert data exactly

- Date: 2026-10-28 (pre-window)
- Status: accepted

## Context
The subset rule ([0001](0001-strict-subset.md)) says Fe0's output behaves the same as the
official compiler's. The differential harness can only check that if "the same" means identical
bytes. Probing the official compiler (`spike-layout/`, master `d217a51bf`, from `fe test
--trace-evm` and revert payloads) gave:
- **Storage:** one 32-byte slot per plain field, in declaration order from 0, with no packing.
  `true` is stored as 1. Fe 26.6.0 packs narrow fields into shared slots (#1826), and Fe0
  follows it. SPEC §6 has the current rule.
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
