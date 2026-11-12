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
argotorg/fe#1989 is open, from `nikicat:native-aarch64-linux` (three commits: the gate
`17734f510`, `Platform` and `target_arch` `839f3a2e3`, and the newsfragment `90d27f083`).
On AArch64 Linux, on the final code: native_runtime 78/78, cli_output 1207/1207, corelib,
ty_check, project_target and the fe unit tests pass, and clippy is clean. frontend's
`deeply_nested_malformed_type_paths_are_resolved_once` overflows its stack in a debug build
here, on master too. `make check-notes` cannot download its tool on AArch64. Follow-ups that
stay out of this PR are in Tw56pax.

## Next
Answer review comments on #1989. When a release includes it, drop our fork and the
WORKAROUNDS.md entry.
