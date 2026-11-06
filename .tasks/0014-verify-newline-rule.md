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
The random generator (T0007) found one place where Fe reads a line break differently. After a
line that ends with a name, Fe reads a line that starts with `{` as a record literal of that
name. So `let a: u256 = x` followed by `{ a }` is rejected (`2-0006`, "expected type here,
but found field"), and so is `s = t` followed by `{ … }`. Fe0 accepts both. Seeds 73, 86,
148, 152, 181, 192 and 220 hit it. `let a: u256 = x + 1` or `= (x)` followed by `{ a }` is
fine. `tools/gen.py` puts such a tail in parentheses until Fe0 rejects it.

## Next
Make Fe0 reject a line that starts with `{` after a line that ends with a name, and add
reject probes for it. Then look for more such cases with a parser differential, as the Goal
says.
