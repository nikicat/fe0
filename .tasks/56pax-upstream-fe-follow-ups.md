---
status: todo
tags: [upstream]
---
# Upstream Fe follow-ups after the AArch64 PR

## Goal
The unsmell run of Nov 11 on the AArch64 PR branch (`/workspaces/fe-master`,
branch `native-aarch64-linux`) found smells that the PR does not fix. Each one
below says where it is, what is wrong and a fix. Each would be its own upstream
PR. The AArch64 PR, argotorg/fe#1989, was merged on Nov 12. Done means each is
sent upstream or dropped with a reason, and the fork is dropped (below). Findings and patches: `.git/unsmell/20261111-224656/` in fe-master.

## The platform (from code the PR changed)
- **p1. `Option<Platform>` means two things** (findings x-2, b1-3, b2-3, b3-4).
  None means "this code has no OS" (EVM, WebAssembly, SP1 guests) and also
  "native code on a host that native code does not support". On such a host,
  `fe check` and `--emit ir` compile with every `target_os` and `target_arch`
  cfg false, as for an SP1 guest. The platform is also worked out twice:
  `BuildBackend::platform` (crates/fe/src/main.rs) gives SP1 None, and
  `project_target::set_target` (crates/driver) gives the host to every
  `Target::Native`, SP1 included. The language server uses the second. Fix:
  make the platform part of the target, such as `Target::Native(Option<Platform>)`,
  set by one setter, and make an unsupported host an error at the edge.
- **p6. The fallback native runner** (crates/fe/src/test/native.rs, the
  `cfg(not(any(target_os = "linux", target_os = "macos")))` `run`) cannot be
  reached, because `prepare_tests` fails first through `Platform::require_host`.
  Its message, "native tests require Linux or macOS", is wrong for x86-64
  macOS. Fix: gate the runner on `cfg(native_host)`, and make the fallback
  `unreachable!()` or use `UnsupportedHost`'s text.

## Upstream code the PR does not change
- **p2.** `TargetConflict.first`/`.other` and `CommonTarget`
  (crates/driver/src/project_target.rs) hold `(String, Target)`, read as `.0`
  and `.1`. Fix: a named `PartTarget { part, target }`.
- **p3.** `dependency_target_mismatch` (same file) returns `Option<String>`, a
  formatted message. Fix: a typed mismatch with a `Display`, like `TargetConflict`.
- **p4.** Four tests in crates/driver/tests/corelib.rs (about lines 509-671)
  repeat the same 18-line check that a string literal has type `DynString`.
  Fix: one helper that each test calls.
- **p5.** `build()` and `check()` (crates/fe/src/build.rs, check.rs) each
  finish the report twice: write the manifest, tar the directory, clean up and
  print. They also take 13 and 9 parameters. Fix: a report-staging type with
  `finish(has_errors)`, and one options struct per command.
- **p7.** native_runtime.rs (`native_runner_bounds_time_and_combined_output`)
  and cli_output.rs (about line 865) hand-write the same wait-with-deadline
  loop: `try_wait`, compare with a deadline, kill, panic, sleep. Fix: one
  `test_utils` helper that waits or kills, with the deadline as a `Duration`.
- **p8.** `prepare_suite_job` (crates/fe/src/test/mod.rs, about line 1432) builds
  the same setup-failure `PreparedSuite` three times, and returns an unnamed
  `(PreparedSuite, String)`. Fix: `PreparedSuite::setup_failed(plan, err)`.
- **p9.** `prepare_tests` (crates/fe/src/test/native.rs) builds the C launcher
  source inline between its named steps, and takes 10 parameters. Fix: extract
  `launcher_source(tests)`, and pass the suite settings as one value.

## Drop the fork
- Fe 26.7.0 (Nov 18) includes #1989, and we build with it (ADR 0022). Delete our fork's branch
  `native-aarch64-linux-v26.6.0`.
