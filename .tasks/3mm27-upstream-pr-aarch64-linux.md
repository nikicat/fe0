---
status: doing
tags: [upstream]
---
# Upstream PR: native output on AArch64 Linux

## Goal
Open a PR to argotorg/fe that resolves argotorg/fe#1975. Then Fe builds native executables
and runs native tests on AArch64 Linux, and `std::fs` reads file metadata correctly there.
When a release includes it, our fork and the WORKAROUNDS.md entry can go.

## Decisions
- Started on Nov 11, ahead of T0009, at the user's choice. A release with it will probably
  come after Nov 24, so our fork stays the workaround in the window.
- The PR is complete. Opening the `Os::host()` gate alone would make `std::fs` read the wrong
  field as a file's mode on AArch64, with no error (offset 24 instead of 16).
- Use a `target_arch` cfg (option a in our #1975 comment). sbillig chose it on Nov 11. Fe's
  `#[cfg]` gains a `target_arch` predicate beside `target_os`, and `sys/linux.fe` gives
  `stat_mode` its AArch64 offset (16) under it. The maintainers plan cross-target builds later
  (as in zig), so the architecture comes from the compilation target, carried in
  `CompilationSettings` like the OS, not from the host.
- The OS and the architecture are one domain type, `Platform { os, arch }`.
  `CompilationSettings.os: Option<Os>` becomes `platform: Option<Platform>`, because the two
  are always set together. `Platform::SUPPORTED` lists the native platforms once, and
  `Platform::host()` picks the host's from it. A cross build later only picks another one.
- The PR text does not name or quote this project (PLAN.md risk 5).

## State
Branch `native-aarch64-linux` in `/workspaces/fe-master` (a clone of argotorg/fe, remote
`fork` = nikicat/fe), on master `1f247d1b1`, two commits, not pushed:
1. `17734f510`, the gate, cherry-picked from `native-aarch64-linux-v26.6.0`.
2. `839f3a2e3`: `Platform { os, arch }`, the `target_arch` cfg (a private `CfgPredicate` in
   `crates/hir/src/core/lower/attr.rs`), `stat_mode` at offset 16 on AArch64, and the
   cleanups from the unsmell run of Nov 11 (`Platform::require_host`,
   `BuildBackend::database`, a 60-second deadline in one native test).
On AArch64 Linux: cli_output 1207/1207, corelib, ty_check, project_target and the fe unit
tests pass, and clippy is clean. native_runtime passed 77 of 78 before the last cleanups,
and the deadline test passed alone after its fix. frontend's
`deeply_nested_malformed_type_paths_are_resolved_once` overflows its stack in a debug build
here, on master too, so it is not ours. Follow-ups that stay out of this PR are in Tw56pax.

## Next
1. Optional: run `native_runtime` once more on the final commit (about 30 minutes).
2. With the user's go-ahead, push to the fork and open the PR with "Fixes #1975". Add the
   newsfragment `<PR>.feature.md` once the PR has a number.
