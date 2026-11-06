---
status: todo
tags: [checker, subset]
---
# Reject locals named after Fe's prelude types

## Goal
Fe 26.5.1 rejects a local whose name is a type or an enum variant that its prelude brings into
scope. `let i32: u256 = 0` gives `8-0000` (type mismatch) and then `8-0030` ("`type` cannot be
used as a value") at each use. Fe0 accepts such names, which breaks the subset rule (SPEC.md).
The random generator (T0007) found it with loop counters named `i8`, `i16` and `i32`.

Done means: Fe0 rejects these names wherever it declares a value (`let`, `var`, parameters,
arm bindings), SPEC.md §1 lists them, and `corpus/reject/` has a probe for each kind of
declaration.

## State
Probed `let NAME: u256 = x` on 26.5.1:
- **Rejected:** `u8` … `u256`, `usize`, `i8` … `i256`, `isize`, `bool`, `String`, `Address`,
  `Option`, `Some`, `None`, `Result`, `Ok`, `Err`, `Evm`, `Bytes`, `Vec`, `Text`, `Sol`,
  `Wei`, `Panic`, `MemVec`, `MemBuffer`, `MemSlice`, `MemSpan`, `MemArray`,
  `FixedMemBuffer`, `StorageMap`, `Duration`, `Timestamp`.
- **Accepted:** functions and traits, such as `panic`, `todo`, `assert`, `revert`, `sol`,
  `cast`, `offset`, `Ctx`, `Log`, `Call`, `Create`, `Abi`, `Clone`, `Default`, `Copy`,
  `Encode`; and `core`, `std`.

The preludes are `ingots/core/src/prelude.fe` and `ingots/std/src/prelude.fe` in Fe's
repository. Master's may differ from 26.5.1's.

## Next
- Probe parameters, arm bindings, fields, function names and constant names the same way.
- Decide whether Fe0 rejects only the probed names or every name that starts with an
  uppercase letter or matches `[ui][0-9]+`. A wider rule is simpler and still allowed by the
  subset rule.
