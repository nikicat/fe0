---
status: todo
tags: [compiler, size, unsmell]
---
# One label table for Gen.stub and Gen.fn_label

## Goal
`Gen.stub` and `Gen.fn_label` (fe0/src/codegen.fe) each write the same rule: take a label
from a table slot, and on first use allocate a new label into the empty slot. A rule written
twice drifts when one copy changes. Done means one named method owns it, or a measurement
shows that it makes Back larger and a comment at both sites records that (Fe 26.7.0, -O s).

## Next
Try a `Refs` method, or a small `LabelTable` type over `MemVec<LabelSlot>`, that returns the
label and whether it is new. `fn_label` adds the FN to `todo` when it is new. Measure Back
with `tools/chain_check.py`.

Found by unsmell run 20261119-211753 (finding b3-9).
