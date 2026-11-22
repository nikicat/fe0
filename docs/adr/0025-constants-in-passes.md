# 25. Constants are evaluated in passes, not on first use

- Date: 2026-11-20
- Status: accepted

## Context
A constant may refer to a later constant ([0001](0001-strict-subset.md), SPEC §5.3), so its
value may depend on constants that are not evaluated yet. On
chain, the EVM stack bounds recursion (DESIGN.md §8a, [0012](0012-max-depth.md)). The parser's
depth cap, `MAX_DEPTH`, bounds the nesting of one expression, but not a chain of constants.

## Decision
The checker evaluates the constants before any body, in passes over the items
(`Checker.constants` in `fe0/src/check.fe`). A pass skips a constant that refers to one not
evaluated yet. A pass that evaluates none reports a cycle (`N006`).

## Alternatives
- **Evaluate a constant on its first use:** this recurses once per constant in a chain, and
  nothing bounds the length of a chain.

## Consequences
- The checker's recursion depth does not grow with a chain of constants.
- A chain of n constants in reverse order takes n passes.
