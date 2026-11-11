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
- Read metadata with `statx` (option c in our #1975 comment). Its layout is the same on every
  Linux architecture (glibc 2.28 and later). It needs no new language surface, unlike a
  `target_arch` cfg (option a), and no run-time switch (option b). The PR says why, and offers
  a or b if the maintainers prefer one.
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
2. On Linux, read metadata with `statx(AT_FDCWD, path, 0, STATX_TYPE | STATX_SIZE, buf)`:
   `stx_mode` is a `u16` at offset 28, and `stx_size` a `u64` at offset 40. Keep `stat` on
   macOS. Check the offsets with a C program on both architectures, as for the comment.
3. Run Fe's `std::fs` tests and the native suites (`native_runtime`, `cli_output`) on AArch64
   Linux. The suites take over an hour on this host. Get x86-64 coverage from Fe's own CI.
4. Open the PR with "Fixes #1975", and link it from the issue.
