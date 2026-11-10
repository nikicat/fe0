# Workarounds for the Fe compiler

Known compiler issues and the shapes we use instead. The toolchain is **Fe 26.5.1**, as
pinned in `.github/workflows/ci.yml`.
Each entry says where it bites, what we do instead, and its upstream status.
Each workaround also says when it can be removed: the release, fix or check that ends it.
A bug is listed as open while Fe master still has it, and as fixed upstream once master
passes it. We stay on 26.5.1 until the submission ([ADR 0009](adr/0009-freeze-on-26-5-1.md)),
so a fix on master removes nothing before we move to a release that has it.

## Language idioms (not bugs, but they cost time)

- `var` declares a mutable local.
- Fe has no `loop`, so write `while true`.
- `as` only allows provably lossless casts. `i32 → u256` needs `.downcast_truncate()`, and so
  does `usize → u64` (because `usize` is 256-bit on the EVM).
- A shift amount must have the same type as the shifted value.
- `MemVec[i]` yields an access, so bind a non-`Copy` element with `let x = ref v[i]`.
- `MemVec` has no `span()`. Use `.into_array().span()` instead, and
  `Bytes::from_payload(source: v.into_array().span())` to make `Bytes`.
- An untyped `"fn".as_bytes()` is `Bytes`, which has no `Index`: use `.byte_at(i)`, or type the
  literal as `String<N>`.
- `String<N>` holds at most 31 bytes. Longer literals are `DynString` (`len()`, `byte_at(i)`).
  Test sources go through `io::text(DynString)`.
- `MemVec` has no `Default`, so use `core::mem::replace(mut place, MemVec::new())`, not `take`.
- `Result<E, T>` puts the error type first. `unwrap()` needs `E: Encode<Sol> + AbiSize`, which
  `#[abi]` on the struct provides.
- An attribute must sit on its own line (`#[test]` then a newline, then `fn`).
- An argument must be labelled unless its parameter is declared as `_ name`.
- A unit `recv` arm needs `Name {}` before its body.
- **Compile time:** `fe test -O 0` is about 3× faster than `-O 1` and 6× faster than the
  default. Use `-O 0` while iterating. CI runs `fe test` in `fe0/` at the default level,
  because that is what deploys. The corpus and generated-programs steps run `tools/embed.py`
  and `tools/gen.py`. These pass `-O 1` to `fe test` unless `-O` is given.

## Open bugs (26.5.1)

- **On the EVM backend, `fe test` compiles each test alone.** Each test becomes its own
  object, with everything it reaches. So a test that calls Fe0 compiles the whole compiler,
  which takes 11 to 13 s of CPU.
  - **Where it bites:** the differential tests (DESIGN.md §10). With one test per program, the
    cost grows with the number of programs. ADR 0003 gives the measurements.
  - **Upstream:** the feature request argotorg/fe#1967 asks for code that many tests share to
    compile once. It is open.
  - **Workaround:** `tools/embed.py` runs one test per batch ingot, which calls every program
    of the batch. It runs the reject tests on `--backend native`, which builds all of them
    into one executable.
  - **Remove when:** a release we use compiles shared code once per suite (#1967), and one
    test per program then runs about as fast as one test per batch.

- **`fe fmt` breaks long lines into code that Fe does not parse.** It moves a binary operator
  such as `<` or `<<` to the start of the next line. The parser then rejects that line with
  "line-start `<` is ambiguous" (`1-0001`), even though `fe fmt` exits with 0. The random
  generator (DESIGN.md §11) found it.
  - **Reproduction:** a `let y: bool = …` whose comparison is longer than the line width.
  - **Upstream:** The bug is still on master `b182b0126`. The open PR argotorg/fe#1523
    targets this class of bug, but we have not tested it. Our reproduction is in a comment on
    that PR.
  - **Workaround:** `tools/embed.py` writes the program modules of its batch ingots without
    formatting them.
  - **Remove when:** `fe fmt` of a release we use turns the reproduction into code that
    parses.

- **Some one-field structs cost bytecode at `-O s`** (argotorg/fe#1964). A one-field struct
  such as `Pos` or `NodeId` is usually free. Four shapes are not:
  - A constant struct passed as an argument to a call. Fe lowers it as data. Passing
    `EMPTY_LIST` to `begin` in `fn_item` cost 610 bytes.
  - A struct field nested in a struct that is stored in bulk or read often. A `Pos` field cost
    31 bytes in `Diag` and 105 in `Node`, and `Parser.at: TokIdx` cost 338.
  - A small accessor that the optimizer stops inlining once it has a few callers.
    `Checked.storage_slot` cost 240 bytes, and `Span.start()` cost 208.
  - A vector of one-field structs. A `MemVec<NodeId>` beside a `MemVec<usize>` cost 280
    bytes in `Ast.lists`.
  - **Workaround:** `fn_item` in `fe0/src/check.fe` passes the FN node's `use_list()`, which is
    always `EMPTY_LIST`. `Parser.expr` in `fe0/src/parser.fe` passes `NOT_BINARY.tighter()`
    instead of the constant `LOOSEST`, which cost about 650 bytes. `Node` and `Diag` store a
    plain offset and rebuild the `Pos` in `pos()`. `Parser.at` stays a plain number, and
    `Span.start` stays a field. `Ast.lists` keeps each list as its length followed by its
    NodeIds in one `MemVec<usize>`.
  - **Remove when:** a release we use fixes #1964. Re-measure each shape first, and undo
    only those that no longer cost bytes.

- **Native builds and native tests refuse AArch64 Linux.** `fe build --backend native -e
  executable` stops with "native executable output currently requires an x86-64 Linux or
  AArch64 macOS host", and `fe test --backend native` stops the same way. Only two
  hard-coded host checks block it: Cranelift and the linking already support AArch64 Linux.
  - **Where it bites:** the dev container on an arm64 host. There, the native reject tests
    of `tools/embed.py`, the native spikes and the native CLI (`fe0-cli`) do not build.
  - **Upstream:** the check is still on master. The issue argotorg/fe#1975 asks to open it,
    with the patch. It is open.
  - **Workaround:** on an arm64 host, build 26.5.1 from source with the two checks opened,
    and pass it as `FE=…` (or as the argument of `tools/spikes.sh`). With it, Fe's own
    native tests pass (34 and 685), and so do our corpus, reject programs and spikes
    (Nov 10). CI runs on x86-64 with the official release, so it needs no patch.

    ```sh
    git clone --depth 1 --branch v26.5.1 https://github.com/argotorg/fe.git fe-26.5.1
    cd fe-26.5.1    # add aarch64 Linux to native_executable_host_supported() in
                    # crates/fe/src/build.rs and to the check in crates/fe/src/test/native.rs
    (cd crates/tree-sitter-fe && npm ci)
    cargo build --locked --profile dist -p fe --features fe/cranelift   # target/dist/fe
    ```
  - **Remove when:** a release we use builds native code on AArch64 Linux (#1975), or the
    dev container runs on an x86-64 host.

## Upstream API churn (master, unreleased)

- **Master removes character I/O from `std::io`** (newsfragment `+native-io.removal`).
  `Read`, `Write`, `read_char`, `write_char`, `host()` and `main(argc, argv)` are gone.
  `Stdout`/`Stdin` effects, `print!` and `StdinReader` replace them.
  - So the compiler core reads its input through **its own `fe0::io::Source` effect**
    ([ADR 0010](adr/0010-source-effect.md)). Only the edge adapters touch std.
  - The native CLI (`fe0-cli`) is not written yet. It will use 26.5.1's `std::io`, and it
    needs a port to the new API only if we leave 26.5.1. Its stderr workaround (below)
    becomes `eprintln!` then.

- **Master makes `DynString`, `Bytes` and `DynArray` own their memory** (newsfragment
  `1914.removal`, commit `e2a0bb8d7`). They are no longer `Copy`, and `DynString::as_bytes` is
  gone. Master also renames `MemBuffer::alloc` to `MemBuffer::new` (`bb6110dff`). So master
  `b182b0126` rejects `fe0` in three places:
  - `fe0/src/io.fe`, `text`: `s.as_bytes()` on a `DynString`;
  - `fe0/src/parser_tests.fe`, `Printer.matches`: `want.as_bytes()`;
  - `fe0/src/difftest.fe`, `theirs`: `MemBuffer::alloc`.

  We stay on 26.5.1 ([ADR 0009](adr/0009-freeze-on-26-5-1.md)), so these stay as they are.
  The two `as_bytes` calls could use `len()` and `byte_at()`, which both versions have. No
  spelling of the `MemBuffer` constructor works on both.
  - **Port when:** we move to a release with `e2a0bb8d7` and `bb6110dff`.

## Fixed upstream (master only; we stay on 26.5.1)

- **A native program has no stderr.** 26.5.1's `std::io` wraps only `getchar` and
  `putchar`. Master adds `Stderr` and `eprintln!` (argotorg/fe#1900).
  - **Workaround on 26.5.1:** declare libc's `malloc` and `write` in an `extern` block, copy
    the bytes into a `malloc` buffer, and call `write(2, buf, len)`.
    `spike-native/probe_stderr.fe` shows it, and `tools/spikes.sh` checks it. The native CLI
    writes its errors this way.
  - **Remove when:** we move to a release with #1900. The CLI then calls `eprintln!`.

- **A native panic is a silent trap.** On 26.5.1, a failed assertion or a panic in a native
  program dies with SIGILL (exit code 132) and prints nothing, not even the panic code.
  Master prints the reason on stderr and aborts (argotorg/fe#1883).
  - **Workaround on 26.5.1:** none. The native CLI exits with 132 on a bug in Fe0, and the
    native reject tests re-run on the EVM to get the panic code (DESIGN.md §10).
  - **Remove when:** we move to a release with #1883. The reject tests can then read the
    panic code from stderr and skip the re-run on the EVM.

- **An integer literal too wide for its type is cut short without an error.** `fe check`
  accepts `f(0x100000005)` for a parameter `_ s: u32`, and `f` gets 5. Fe0 has only `u256`,
  so this affects our Fe test code, not the programs Fe0 accepts. Master fixed it in
  `1a890a056` ("Reject integer literals out of range for their type"), so it was not
  reported.
  - **Workaround on 26.5.1:** `Call` in `tools/fegen.py` checks that a selector fits in
    4 bytes before it writes the literal for `difftest::Payload.push_selector`.
  - **Remove when:** we move to a release with `1a890a056`. Then `fe check` rejects such a
    literal itself.

- **The optimizer drops the operand of an unused checked operation, but keeps its check.** At
  `-O 1` and above, `var x: u256 = 2 - (a ^ 5)` with `x` unused and `a = 1` checks `2 - a`
  instead of `2 - 4`. So the call succeeds where it should revert with `Panic(0x11)`. The
  same bug can also add a spurious panic. Master `b182b0126` checks the right operand, and it
  adds no spurious panic. The issue argotorg/fe#1853 is still open, and a comment there holds
  our case.
  - **Where it bites:** generated program seed 99 (`tools/gen.py --seed 99 -n 1`) fails at
    `-O 1` and `-O 2`, and passes at `-O 0`. The tools use `-O 1` by default (see Compile
    time). CI runs seeds 1–25, which do not hit it.
  - **Workaround on 26.5.1:** none in the generator yet.

- **The backend panics on a shift by a large constant.** `x << C` or `x >> C`, where `x` is
  not a constant and `C` is a constant of 2⁶⁴ or more, makes `fe build` and `fe test` panic
  with "Integer overflow when casting to usize" (in `primitive-types`), at every `-O` level.
  `fe check` accepts the program. The random generator found it. Master `b182b0126` compiles
  it at every level and gives 0, probably through its newer Sonatina, so it was not reported.
  - **Reproduction:** `fn h(_ x: u256) -> u256 { x << 0x10000000000000000 }`, called from an
    arm with `h(x)` or `h(5)`.
  - **Workaround on 26.5.1:** `BodyWriter.shift_amount` in `tools/gen.py` keeps every shift amount
    below 512 outside constant declarations, where the shift folds.
  - **Remove when:** a release we use compiles the reproduction.

- **Same-named contracts in two modules** crash codegen (argotorg/fe#1887, fixed by #1890).
  `fe test` fails with `InvalidCodeRegion`, and `fe build` fails with "duplicate root object
  `C` across ingot modules" (`spike-deps/dupname`). The harness still gives every contract a
  unique name (DESIGN.md §10).
  - **Remove when:** we move to a release with #1890, and `spike-deps/dupname` passes on it.
- **Native keccak** (argotorg/fe#1886, fixed by #1909). On 26.5.1 the native `Hasher` still
  needs the software keccak (DESIGN.md §12).
  - **Remove when:** we move to a release with #1909. The native `Hasher` then calls std's
    keccak.
- **`enum.extract requires an initialized payload subtree` (IR0600)**, an internal error at
  `-O 1` and above; `-O 0` works. Fixed on master `95ec05413`, probably by its newer Sonatina,
  so it was not reported.
  - **Trigger:** `?` on a `Result<E, T>` inside a `while true` loop, in a function whose own
    `Result` the caller then matches or unwraps. A 46-line reproduction is in
    `spike-harness/ice-min/repro.fe` (git-ignored); run it with `fe test -O 1 repro.fe`.
  - **Workaround on 26.5.1:** `Lexed` and `Ast` carry an `err: Option<Diag>` field instead of
    being a `Result` ([ADR 0011](adr/0011-error-field-not-result.md)).
  - **Remove when:** a release we use compiles `repro.fe` at `-O 1`. Then `Lexed` and `Ast`
    can become `Result`s again, if that costs no bytecode, and ADR 0011 is superseded.
