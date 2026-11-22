# 29. CI does not run `node_check.py --levels`

- Date: 2026-11-22
- Status: accepted

## Context
`tools/node_check.py` deploys and calls each program's Fe0 build and its Fe build on anvil and
compares them (DESIGN.md §10). With `--levels`, it also builds each program with Fe's other
optimisation levels and compares each build with the reference level's, to find bugs in Fe. It
reports their differences separately, and they do not change the exit status. On the corpus and
`corpus/gen/`, it makes a `node_check.py` run take 380 s instead of 119 s, and it finds no
difference (Fe 26.7.0). Fe is pinned ([0022](0022-move-to-26-7-0.md)).

## Decision
CI does not run `node_check.py --levels`. Fe is pinned, so a new difference could come only
from a new or changed program. It is run by hand after such a change or an upgrade of Fe.

## Alternatives
- **Run it in CI:** each run would take 380 s instead of 119 s, and on Fe 26.7.0 it finds no
  difference.

## Consequences
- A bug in Fe at another level is found only by a run by hand.
