---
status: doing
deps: [T0005]
due: 2026-11-18
tags: [native]
---
# Native CLI (`fe0-cli`)

## Goal
A native executable that reads Fe0 source on stdin and prints the bytecode as hex. It is the
only place that touches std I/O (26.5.1's `std::io`; master removed it, see WORKAROUNDS.md).
Its output must match the on-chain compile byte for byte.

## Design (draft, for review)

### What 26.5.1 gives us
- `std::io` has only `getchar` and `putchar` behind `HostIo`. So there is stdout, but no
  stderr and no files.
- `main(argc: i32, argv: **u8) -> i32` is the entry point. Its result is the exit code.
  `std::native::Args` reads the arguments.
- A user ingot may declare its own `extern { fn … }`. `fe check` accepts one.
- A panic in a native executable is a SIGILL trap, with no panic code.
- `fe build --backend native -e executable` builds only on x86-64 Linux and AArch64 macOS.
  `fe test --backend native` has the same limit.

### The ingot
- `fe0-cli/` holds the ingot `fe0_cli`. It depends on `fe0` by path, and the workspace
  `fe.toml` lists it as a member.
- `src/lib.fe` holds `main` and the stdin adapter. `src/messages.fe` holds the messages.

### Reading
- `main` reads all of stdin into memory first, then compiles it through a `Source` over
  those bytes. It does not read stdin while it compiles.
- So, when it reports an error, it has the whole text, and it can turn the offset into a
  line and a column with fe0's `Text.line_col`. That needs `Text::new` and `Text.push` to
  be public. They are private today.
- Programs are a few KB, so holding them twice costs nothing.

### Writing
- On success, stdout gets the deploy code (the initcode, then the runtime code) as lowercase
  hex, with no `0x` and one newline at the end. `fe build` writes its `.bin` files in the
  same form, so the two can be compared with `diff`.
- Errors and warnings go to stderr. An error prints as `<stdin>:line:col: CODE message`, and
  a warning as `<stdin>:line:col: warning: CODE message`.
- 26.5.1's `std::io` has no stderr, so the CLI declares libc's `malloc` and `write` in an
  `extern` block. It copies each line into a `malloc` buffer and calls `write(2, buf, len)`.
  `spike-native/probe_stderr.fe` shows that this works (Nov 10), and `tools/spikes.sh`
  checks it. On master, `eprintln!` replaces it (argotorg/fe#1900).

### Exit codes
- 0: compiled. Warnings may have been printed.
- 1: Fe0 rejected the program.
- 2: an argument was given. The usage line goes to stderr.
- `getchar` returns -1 both at the end of input and on a read error, so a read error looks
  like the end of the program. It has no exit code of its own.
- 132 (SIGILL): a bug in Fe0, such as an assertion that failed.

### Messages
- The message table lives in the CLI, not in `fe0/src/diag.fe`. Only the CLI prints
  messages, so the on-chain compiler does not pay for them in bytecode.
- DESIGN.md §9 says that the table is in diag.fe. That sentence changes with this task.
- A test checks that every `DiagCode` in diag.fe has a message.

### Arguments
- None. Anything in argv is an error (exit code 2).

### The byte-for-byte check
- A new tool, `tools/cli_check.py`, builds the CLI and runs it on every program of
  `corpus/` and `corpus/gen/`.
  - For an accepted program, it writes the hex into a batch test on the EVM backend. The
    test runs `fe0::codegen::compile()` on the same source and asserts that the code is
    equal byte for byte. It reuses the `Batch` machinery of `tools/embed.py`.
  - For a reject program, it checks that the CLI prints the code, line and column of the
    program's header, and exits with 1.
- CI runs it after the corpus step.

## Decisions
- Develop and test the CLI on this aarch64 Linux host with a patched Fe 26.5.1, at
  `/workspaces/fe-26.5.1/target/dist/fe` (`FE=…`). Stock 26.5.1 refuses native builds on
  aarch64 Linux, and the patch only opens that gate (argotorg/fe#1975). CI and the
  submission keep the official release.
- Errors to stderr through `extern write`, not to stdout. The spike above showed it works.
- No CLI parsing library: the CLI takes no arguments, and Fe has no such library.

## State
- Steps 1 to 3 are done, and the CLI is finished:
  - fe0 gives the CLI `Text::of`, which builds a `Text` from the bytes read on stdin.
  - `fe0-cli/` (`lib.fe`, `messages.fe`, `stderr.fe`) builds natively in 11 s.
  - `tools/cli_check.py` runs it on all programs and reject programs and checks its code on the
    EVM with `difftest::same_code`. On Nov 10 with the patched Fe: 69 of 69 programs (44 of
    the corpus, 25 generated) give the same code byte for byte, and 70 of 70 reject programs
    give their error. A wrong digit is reported at the right byte. It takes about 30 s.
  - CI runs it after the generated programs.
- A `String<N>` literal shorter than N is padded with zero bytes at the front. The message
  table's `Message.append_to` drops that padding.
- The /unsmell run of Nov 10 reshaped the CLI and the tools. It moved the literal range
  check (L004) to the parser, and gave the Python tools full types (mypy --strict, pyright).
- The README does not exist yet. T0010 writes it, and now lists the CLI's part of it.

## Next
Check that CI passes on x86-64 with the official release, then close the task.
