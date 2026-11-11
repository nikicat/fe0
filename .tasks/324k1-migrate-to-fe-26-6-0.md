---
status: doing
tags: [toolchain, upstream]
---
# Move to Fe 26.6.0

## Goal
Fe 26.6.0 was released on Nov 10. It fixes six of our workarounds and makes the compiler
smaller. Done means: CI runs v26.6.0, every suite passes on it, WORKAROUNDS.md lists only what
26.6.0 still needs, and a new ADR replaces ADR 0009 (the freeze on 26.5.1).

## Decisions
- The user approved the upgrade on Nov 11. ADR 0015 records why, with the measurements.
- Test helpers take their source as `own DynString`, not a copy made in `io::text`. The
  generators write the same signatures.
- A module with EVM tests that a native build reaches starts with `#![cfg(target = "evm")]`.
  With that gate, fe0-cli's fe.toml sets `target = "native"`, so the editor checks it as the
  native program it is.
- The lexer gas baseline in `tools/spikes.sh` moves to 704,464, the same source measured on
  26.6.0 (802,865 on 26.5.1).
- `tools/gen.py` keeps its shift mask, which keeps most shifts from giving 0. It now leaves
  one shift amount in ten unmasked, which 26.5.1's backend could not compile.

## State
All in the working tree, not committed:
- ADR 0015, with ADR 0009 marked superseded.
- The port of fe0, fe0-cli, the generators and the spikes.
- `loop` reserved: SPEC, lexer, lexer test, and `corpus/reject/reserved_loop.fe`.
- The `shadow_item_bind` header and SPEC §5.2.
- WORKAROUNDS.md rewritten, DESIGN.md §10 and §12, PLAN risks, and tasks T0009, T0010, T0012.
- The dev container, which CI runs in, pins v26.6.0, with the new sha256 for each architecture.

The output of 26.6.0 has no opcode newer than Cancun. It ends in the same data bytes as
26.5.1's.

The fork branch `native-aarch64-linux-v26.6.0` is at `/workspaces/fe-26.6.0`, as a worktree
of `/workspaces/fe-26.5.1`. It holds the gate patch as commit `c1227e79a`, pushed to
nikicat/fe. #1975 has a comment about 26.6.0 (Nov 11). The official binary is at
`target/fe-official` there.

## Next
1. Commit here and push. The first CI run builds the dev container image (devcontainers/ci)
   and pushes it to GHCR from main. Check that it passes, and that later runs reuse the image.
   Close this task once CI passes.

Then T0009, then the upstream PR (T3mm27), which starts from the gate commit above.
