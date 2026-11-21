---
status: todo
tags: [tools, testing]
---
# Pin the reference behaviour

## Goal
Fe0 compiles a subset of Fe. The subset rule (top of SPEC.md) compares Fe0's build of a program
with Fe's build at `-O 1`, the level the differential tests use (DESIGN.md §10). Fe also builds
at `-O 0`, `2` and `s`, and nothing checks that those levels agree with `-O 1`. A Fe bug at one
of them would go unnoticed.

Done means:
- a check also builds Fe's side at its other levels, and reports a difference between two of
  Fe's levels as a Fe bug, in its own section of the output, without failing on it;
- that check runs in CI, or this task says why not.

## Decisions
- The reference level is `-O 1`. Fe's other levels are checked only for Fe bugs: a difference
  among Fe's builds is reported, and it does not fail the check.

## State
- For each deployment and call, `node_check.py` compares success, return or revert data, logs
  and the storage slots that changed. A difference between two of Fe's levels would show in one
  of these.
- No miscompile that depends on the level is known on Fe 26.7.0 (docs/WORKAROUNDS.md).
  argotorg/fe#1853 is an example of one: on Fe 26.5.1, at `-O 1` and above, the optimiser
  dropped the operand of an unused checked subtraction. It checked `2 - (a ^ 5)` as `2 - a`, so
  a call that should revert with an overflow succeeded.
- `node.Build`, the enum of builds, has the level members `FE_O1` and `FE_OS`, and
  `node_check.py -O s` compares Fe0 with `-O s`. `node_check.py` defaults to `-O 1`. Nothing
  compares Fe's levels with each other, and there is no `-O 0` or `-O 2` build.

## Plan
1. **Add the cross-level check to `node_check.py`.** Add `FE_O0 = "0"` and `FE_O2 = "2"` to
   `node.Build`. Add a `--levels` option that also deploys Fe's builds at the other levels, and
   compares each with Fe's build at the level that `-O` names (default `-O 1`), using
   `differences` in node_check.py, which lists the fields where two builds' effects differ. A
   difference among Fe's builds is printed under its own heading, such as "Fe -O 0 and Fe -O 1
   differ". The exit status is 1 only for Fe0's differences. A build or deployment that fails at
   only one of Fe's levels counts as a difference among Fe's builds.
2. **Measure the cost** on the dev container, with nothing else running, since the host has
   little memory and parallel runs skew the times. Time `node_check.py` against
   `node_check.py --levels`, over corpus/ and the generated programs in corpus/gen/. Each extra
   level adds one `fe build` per program, and one more deployment and run of the program's call
   script. A run now does two builds per program (Fe0's and Fe's at `-O 1`), so three extra
   levels may more than double the step. Step 3 has fallbacks for that.
3. **CI.** In .github/workflows/ci.yml, the "programs on a node" step runs `node_check.py`. If
   `--levels` adds under about a fifth to its time, run it there. Otherwise run it in a
   separate, non-blocking step, only on the corpus, or with fewer levels. Record the choice and
   its measured time in DESIGN.md §10, tagged with the toolchain, as in "(Fe 26.7.0)".
4. **Report a Fe bug if one shows up.** File it upstream, and add a docs/WORKAROUNDS.md entry.

## Next
- Wait until after T0010, the contest submission. Code changes stop at its freeze on Nov 23,
  when the release is tagged and deployed. These steps change the tools and CI, and step 1 may
  find a Fe bug that needs work right before the release.
