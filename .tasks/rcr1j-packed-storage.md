---
status: doing
tags: [codegen, spec, bug]
---
# Pack storage fields as Fe 26.6.0 does

## Goal
Fe 26.6.0 packs consecutive contract fields narrower than a slot into one slot, as Solidity
does (Fe's CHANGELOG, #1826): an `Address` takes 20 bytes and a `bool` 1 byte, from the low
end of the slot, and a `u256` takes a whole slot. Fe0 still puts each field in its own slot,
as SPEC.md §6 says ("one 32-byte slot per field with no packing [✓]", which was true on
26.5.1). So Fe0's storage layout differs from Fe's, against ADR 0002. Done means Fe0 packs the
same way, SPEC §6 and DESIGN describe it, and `tools/node_check.py` reports no difference on
the corpus.

## Found
`tools/node_check.py` (ADR 0016, step 0) on Nov 12. Four corpus programs differ in their
storage writes: `owner.fe` (`pending: Address, has_pending: bool` share slot 1 in Fe),
`init_args.fe`, `no_init.fe` (`Address` then `bool`) and `voting.fe` (`closed: bool,
passed: bool` share slot 3). The in-EVM harness could not see it, because each build reads its
own layout back consistently.

## Next
1. Probe Fe's rule on the edges: a `bool` after 31 used bytes, an `Address` after 12, a `u256`
   between two `bool`s, and whether the `u256` after packed fields starts a new slot.
2. The checker assigns each field a slot and a byte offset. Code generation reads a packed field
   with `SLOAD`, a shift and a mask, and writes it by reading the slot, clearing the field's
   bytes, and `OR`ing the new value in.
3. Measure the code generation contract's size, and rerun `tools/gas_compare.py`: packing saves
   `SSTORE`s, so the ratios of `owner`, `voting`, `init_args` and `no_init` change.
