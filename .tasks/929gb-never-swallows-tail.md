---
status: todo
tags: [checker, subset]
---
# A diverging statement must not hide the block's tail

## Goal
Once a statement has type `TY_NEVER`, `block` in `fe0/src/check.fe` ignores the tail. So
Fe0 accepts programs that Fe rejects:
- a tail of the wrong type after `return` (Fe: 8-0000);
- `break` followed by `5` in a while body (Fe: 8-0031).

Done means: a block with a tail has the tail's type, and is `TY_NEVER` only when it has no
tail and a statement diverges. SPEC.md §5 states the typing rule, and reject probes cover
both cases.

## Next
Probe what Fe does with an unreachable tail of the right type (`return 1` then `2`), so
that the rule doesn't reject more than it needs to.
