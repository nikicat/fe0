---
status: todo
deps: [T324k1, T0009]
tags: [upstream]
---
# Upstream PR: native output on AArch64 Linux

## Goal
Open a PR to argotorg/fe that resolves argotorg/fe#1975. Then Fe builds native executables
and runs native tests on AArch64 Linux, and `std::fs` reads file metadata correctly there.
When a release includes it, our fork and the WORKAROUNDS.md entry can go.

## Decisions
- Scheduled after the 26.6.0 move (T324k1) and after T0009 (due Nov 21). The PR does not
  help us in the window, because a release with it will probably come after Nov 24.
- The PR is complete. Opening the `Os::host()` gate alone would make `std::fs` read the wrong
  field as a file's mode on AArch64, with no error (offset 24 instead of 16).
- Use a `target_arch` cfg (option a in our #1975 comment). sbillig chose it on Nov 11. Fe's
  `#[cfg]` gains a `target_arch` predicate beside `target_os`, and `sys/linux.fe` gives
  `stat_mode` its AArch64 offset (16) under it. The maintainers plan cross-target builds later
  (as in zig), so the architecture comes from the compilation target, carried in
  `CompilationSettings` like the OS, not from the host.
- The PR text does not name or quote this project (PLAN.md risk 5).

## State
- The gate part is on the branch `native-aarch64-linux-v26.6.0` of nikicat/fe
  (`/workspaces/fe-26.6.0`). It changes `Os::host()` in `crates/common/src/compilation.rs`
  and the AArch64 Linux test gates in `crates/fe/src/test/native.rs`,
  `crates/fe/tests/native_runtime.rs` and `crates/fe/tests/cli_output.rs`.
- `std::fs` calls `stat` through an extern in `ingots/std/src/fs.fe`. `sys/linux.fe` reads
  `st_mode` at 24 and `st_size` at 48. The other values in `sys/linux.fe` are the same on
  AArch64 (the table in our #1975 comment).

## Next
1. Branch from Fe master, not from the release. Port the gate commit to it.
2. Add `target_arch` to cfg: the target's architecture in `CompilationSettings` (beside the
   OS that `Os::host()` gives), its evaluation in HIR's cfg lowering
   (`crates/hir/src/core/lower/attr.rs`, which knows `target`, `target_os` and
   `target_family`), CLI.md's cfg docs and tests. Then split `stat_mode` in `sys/linux.fe`.
3. Run Fe's `std::fs` tests and the native suites (`native_runtime`, `cli_output`) on AArch64
   Linux. The suites take over an hour on this host. Get x86-64 coverage from Fe's own CI.
4. Open the PR with "Fixes #1975", and link it from the issue.
