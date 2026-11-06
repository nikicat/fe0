---
status: todo
tags: [docs, unsmell]
---
# SPEC §8 describes a harness that does not exist yet

## Goal
SPEC §8 says the official build is deployed with `evm.create2<C>` and that storage reads are
compared. The codegen differential tests (`fe0/src/codegen_tests.fe`) deploy both builds with
`create_raw` (the official initcode comes from `C::init_code_offset()`) and observe storage
only through calls. Make §8 state what every differential test must compare, and leave how to
DESIGN §10, once T0006's harness settles it.

Found by the /unsmell run of 2026-11-05 on T0005 (finding x-3).
