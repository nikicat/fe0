---
status: todo
deps: [T0006]
tags: [spec]
---
# Verify the newline rule against Fe

## Goal
The last [V] item in SPEC.md §3.4: does Fe read every line break Fe0 accepts the same way? Run a
parser differential over the whole corpus, generated programs included.

## State
The random generator (T0007) found one place where Fe reads a line break differently: after a
line that ends with a name, Fe reads a line that starts with `{` as a record literal of that
name. Fe0 now rejects that with `P012` (SPEC.md §3.4), and `corpus/reject/record_literal_*.fe`
are its probes. `tools/gen.py` still puts such a tail in parentheses, so that its programs
stay accepted.

## Next
Look for more such cases with a parser differential, as the Goal says: for each corpus and
generated program, check that Fe and Fe0 split it into the same statements.
