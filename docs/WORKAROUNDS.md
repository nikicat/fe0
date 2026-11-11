# Workarounds for the Fe compiler

Known compiler issues and the shapes we use instead. The toolchain is **Fe 26.6.0**, as
pinned in `.devcontainer/Containerfile`.
Each entry says where it bites, what we do instead, and its upstream status.
Each workaround also says when it can be removed: the release, fix or check that ends it.
We stay on 26.6.0 until the submission ([ADR 0015](adr/0015-move-to-26-6-0.md)), so a fix on
master removes nothing before we move to a release that has it.

## Language idioms (not bugs, but they cost time)

- `var` declares a mutable local.
- `as` only allows casts that are lossless on every target. `usize` is 256 bits on the EVM
  and 64 bits natively, so `u256 as usize` and `usize as u64` are rejected. Use
  `.downcast_unchecked()` or `.downcast_truncate()`, as for `i32 → u256`.
- A shift amount must have the same type as the shifted value.
- `MemVec[i]` yields an access, so bind a non-`Copy` element with `let x = ref v[i]`.
- `MemVec` has no `span()`. Use `.into_array().span()` instead, and
  `Bytes::from_payload(source: v.into_array().span())` to make `Bytes`.
- An untyped `"fn".as_bytes()` is `Bytes`, which has no `Index`: use `.byte_at(i)`, or type the
  literal as `String<N>`.
- `String<N>` holds at most 31 bytes. Longer literals are `DynString` (`len()`, `byte_at(i)`).
  A `DynString` is not `Copy`, so test sources go through `io::text(own DynString)`, and
  each test helper takes its source as `own`.
- `MemVec` has no `Default`, so use `core::mem::replace(mut place, MemVec::new())`, not `take`.
- `Result<E, T>` puts the error type first. `unwrap()` needs `E: Encode<Sol> + AbiSize`, which
  `#[abi]` on the struct provides.
- A module with EVM tests starts with `#![cfg(target = "evm")]` when a native build reaches
  it, as `fe0/src/codegen_tests.fe` does for fe0-cli. A native build type-checks every module,
  and rejects a test that `uses (evm: mut Evm)`.
- A native-only ingot sets `target = "native"` in its `fe.toml`, as fe0-cli does. Without it,
  `fe check` and the editor check the ingot for the EVM, and reject a `main` that uses `Args`
  or `Stdout`.
- An attribute must sit on its own line (`#[test]` then a newline, then `fn`).
- An argument must be labelled unless its parameter is declared as `_ name`.
- A unit `recv` arm needs `Name {}` before its body.
- **Compile time:** `fe test -O 0` is about 3× faster than `-O 1` and 6× faster than the
  default. Use `-O 0` while iterating. CI runs `fe test` in `fe0/` at the default level,
  because that is what deploys. The corpus and generated-programs steps run `tools/embed.py`
  and `tools/gen.py`. These pass `-O 1` to `fe test` unless `-O` is given.

## Open bugs

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
  - **Upstream:** The bug is still in 26.6.0. The open PR argotorg/fe#1523 targets this
    class of bug, but we have not tested it. Our reproduction is in a comment on that PR.
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
  executable` stops with "native executable and library output currently require an x86-64
  Linux or AArch64 macOS host", and `fe test --backend native` stops the same way. 26.6.0
  ships an AArch64 Linux binary (`fe_linux_arm64`), but that binary refuses its own host too.
  Two host checks block it. One is in `Os::host()`, and the other is in the native test
  runner. Cranelift and the linking already support AArch64 Linux.
  - **Where it bites:** the dev container on an arm64 host. There, the native reject tests
    of `tools/embed.py`, the native spikes and the native CLI (`fe0-cli`) do not build.
  - **Upstream:** the issue argotorg/fe#1975 asks to open the checks. It is open. Opening
    them is not quite enough: `ingots/std/src/sys/linux.fe` reads `st_mode` at x86-64's offset
    (24), and AArch64's is 16. So `std::fs` would read the wrong field there. Fe0 does not
    use `std::fs`.
  - **Workaround:** on an arm64 host, build 26.6.0 from source with both checks opened, and
    pass it as `FE=…` (or as the argument of `tools/spikes.sh`). The branch
    `native-aarch64-linux-v26.6.0` of our fork holds `v26.6.0` and one commit that opens
    both checks. With it, our corpus, reject programs, CLI check and spikes pass (Nov 11). CI
    runs on x86-64 with the official release, so it needs no patch.

    ```sh
    git clone --depth 1 -b native-aarch64-linux-v26.6.0 https://github.com/nikicat/fe.git fe-26.6.0
    cd fe-26.6.0
    (cd crates/tree-sitter-fe && npm ci)
    cargo build --locked --profile dist -p fe --features fe/cranelift   # target/dist/fe
    ```
  - **Remove when:** a release we use builds native code on AArch64 Linux (#1975), or the
    dev container runs on an x86-64 host.

## Not checked on 26.6.0

- **`enum.extract requires an initialized payload subtree` (IR0600).** 26.5.1 failed with this
  internal error at `-O 1` and above. The same code compiled at `-O 0`. We have not checked
  this bug on 26.6.0. The reproduction was git-ignored and is lost. A case rebuilt from the
  trigger below passes even on 26.5.1.
  - **Trigger:** `?` on a `Result<E, T>` inside a `while true` loop, in a function whose own
    `Result` the caller then matches or unwraps.
  - **Workaround:** `Lexed` and `Ast` carry an `err: Option<Diag>` field instead of being a
    `Result` ([ADR 0011](adr/0011-error-field-not-result.md)).
  - **Remove when:** `Lexed` and `Ast` as `Result`s pass fe0's tests at `-O 1` on a release
    we use, and cost no bytecode. Then ADR 0011 is superseded.
