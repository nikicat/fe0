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
`fork` = nikicat/fe), on master `1f247d1b1`. Not committed beyond the first commit:
1. The gate commit, cherry-picked from `native-aarch64-linux-v26.6.0` (`17734f510`).
2. In the working tree: `Arch` and `Platform` in `crates/common/src/compilation.rs`,
   `target_arch` in `crates/hir/src/core/lower/attr.rs`, `stat_mode` split in
   `ingots/std/src/sys/linux.fe`, and the callers and tests moved to `Platform`. The cfg
   tests cover both architectures (`crates/uitest/fixtures/cfg/select.fe`) and an unknown one
   (`cfg_attr.fe`). `cargo check --all-targets` and the `ty_check` suite pass.

## Next
1. Run the std analysis (`fe-driver --test corelib`), then the native suites (`native_runtime`
   and `cli_output`) on AArch64 Linux. `native_fs_reads_writes_and_lists_files` must pass now.
2. Commit, push to the fork, and open the PR with "Fixes #1975". Add the newsfragment
   `<PR>.feature.md` once the PR has a number.
