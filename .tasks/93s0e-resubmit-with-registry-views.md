---
status: todo
due: 2026-11-24
tags: [contest]
---
# Resubmit with the playground's registry views

## Goal
The Fe Builders Challenge judges the latest valid submission made before Nov 24, 23:59 UTC.
The current one names `df573be`. Once the playground's registry views (task Tjq40d) are
pushed and CI passes, submit again with that commit's full SHA. The other answers stay the
same. The prefilled form link is in `docs/registration-confirmation.txt`, which must never be
committed.

## Next
Push the registry views (closing Tjq40d), wait for CI on main, then submit with main's HEAD.
