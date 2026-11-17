---
status: todo
tags: [conformance]
---
# Decide the rules that are stricter than Fe on purpose

## Goal
◐ rows of SPEC.md §10 where the code change is small but a recorded decision stands behind
the stricter rule. Each needs a decision (keep, or drop and record why) before any code.
- `uses (log)` and `uses (call)` without `mut` (§6): Fe0 grants a change only through `mut`.
- Locals named like a storage field (`N005`, §5.2): a name never silently stops referring to
  the field.
- Parameters and locals named like items (`N018`, §5.2): Fe's rule differs by kind of name.
- Forward references between constants (`N006`, §5.3): evaluation on first use with cycle
  detection costs Checker bytes, about 2.2 KB left.
