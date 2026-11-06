---
status: todo
tags: [parser, subset]
---
# Comparisons that Fe reads as generic arguments

## Goal
Fe 26.5.1 reads `x < y >> z` as `x<y>` followed by `> z`, and rejects it with `2-0011`
("incorrect number of generic arguments"). Fe0 reads it as a comparison and accepts it, which
breaks the subset rule (SPEC.md). The random generator (T0007) found it in seeds 47 and 145
(`p5 < 0x7be3… >> 256`, `K1 < 2 >> 0X0`).

Done means: Fe0 rejects every such comparison, SPEC.md §3 states the rule, and
`corpus/reject/` has a probe for each shape below. Then `tools/gen.py` can drop the
parentheses that it puts around the left operand of `<`.

## State
Probed on 26.5.1, with `x`, `y` and `z` parameters, `K` a constant and `g` a function:
- **Rejected:** `x < y >> z`, `x < 1 >> 2`, `x < (y) >> z`, `x < g(y) >> z`, `K < y >> z`,
  `x + z < y >> 1`, `x < y | z >> 1 == 0`, `x < y >> z && true`.
- **Accepted:** `x < y + 1 >> z`, `(x) < y >> z`, `5 < y >> 1`, `x <= y >> z`,
  `x < y || y > z`, `x < y && y > z`, `g(x < y, z > x)`.

So the trigger is a name right before `<` (a path, in Fe's grammar), then a `>` or `>>`
later in the same expression. `y + 1` in between stops it, but `y | z` does not.

## Next
Find the rule in Fe's parser (`crates/parser/src/parser/expr.rs`, generic arguments in
expression position). A rule wider than Fe's is allowed: for example, reject a `<` right
after a name whenever a `>` or `>>` follows before the end of the comparison's right operand.
