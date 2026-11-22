# Workarounds for the Fe compiler

Known compiler issues and the shapes we use instead. The toolchain is **Fe 26.7.0**, as
pinned in `.devcontainer/Containerfile`.
Each entry says where it bites, what we do instead, and its upstream status.
Each workaround also says when it can be removed: the release, fix or check that ends it.
We stay on 26.7.0 until the submission ([ADR 0022](adr/0022-move-to-26-7-0.md)), so a fix on
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
- **`fe test` enforces neither EIP-170 nor EIP-3860** (Fe master `d217a51bf`). Runtimes of
  24,577 and 49,152 bytes deploy, and so does 49,153 bytes of initcode. Local `anvil`
  (Foundry 1.8.4, hardfork BPO1) deploys a 24,576-byte runtime and rejects 24,577 bytes. A
  Fe-built `.bin` behaves the same there: the spec Counter returns `get() = 2` after two
  increments, and its runtime is `fe build`'s `.runtime.bin` (99 bytes). So the differential
  tests check both limits on Fe0's builds (`fits_chain` in `fe0/src/difftest.fe`), and
  `tools/chain_check.py` deploys Fe0's own contracts on anvil.
- **Compile time:** `fe test -O 0` is about 3× faster than `-O 1` (Fe 26.5.1). Use `-O 0`
  while iterating. CI runs `fe test` in `fe0/` at the default level. That is the level of the
  reference build of the subset rule (SPEC.md). The corpus and generated-programs steps run
  `tools/embed.py` and `tools/gen.py`. These pass the reference level to `fe test` unless they
  get `-O`.

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
  "line-start `<` is ambiguous" (`1-0001`), even though `fe fmt` exits with 0.
  - **Reproduction:** a `let y: bool = …` whose comparison is longer than the line width.
  - **Upstream:** the bug is in 26.7.0. The open PR argotorg/fe#1523 targets this
    class of bug, but we have not tested it. Our reproduction is in a comment on that PR.
  - **Workaround:** `tools/embed.py` writes the program modules of its batch ingots without
    formatting them.
  - **Remove when:** `fe fmt` of a release we use turns the reproduction into code that
    parses.

- **Some one-field structs cost bytecode at `-O s`** (argotorg/fe#1964). A one-field struct
  such as `Pos` or `NodeId` is usually free. On Fe 26.7.0 at `-O s`, two shapes cost bytes,
  and a third is free.
  - A struct field nested in a struct that is stored in bulk or read often. The `Pos` in
    `Diag` costs the Lexer 185 bytes, the `Pos` in `Node` costs the Parser 665, and
    `Parser.at: TokIdx` costs 24.
  - A vector of one-field structs. A `MemVec<NodeId>` beside a `MemVec<usize>` in `Ast.lists`
    costs the Parser 399 bytes and the Checker 361, and saves Back 91.
  - A small accessor that the optimizer might stop inlining once it has a few callers. This
    shape is free: `Span.start()` costs nothing in any contract. `Span.start` stays a field,
    because an accessor that only returns the field adds nothing.
  - **Workaround:** `Node` and `Diag` store a plain offset and rebuild the `Pos` in `pos()`.
    `Parser.at` stays a plain number. `Ast.lists` keeps each list as its length followed by
    its NodeIds in one `MemVec<usize>`.
  - **Upstream:** #1964 is closed by #1978, "Pass one-scalar constants as values", which is
    in 26.7.0. It makes a fourth shape free, the constant-argument shape, in which a constant
    struct is passed as an argument ([ADR 0022](adr/0022-move-to-26-7-0.md)). No open issue
    covers the two shapes above that cost bytes.
  - **Remove when:** a release we use builds each shape to no more bytes than its workaround.

- **A range `for` costs bytecode at `-O s` when its body makes calls.** A loop such as
  `for k in 0..self.len(l)`, whose body calls methods that are not inlined, compiles to more
  code than a `while` loop over the same index. Six of the list walks in Back, written as
  range loops, make Back 344 bytes larger (measured on Fe 26.6.0 at `-O s`). In a loop whose
  body makes no calls, `-O s` removes the difference.
  - **Probe (Fe 26.6.0):** a loop that only adds numbers is 125 bytes either way at `-O s` (at
    `-O 0` the range loop is 1,768 bytes and the `while` loop 1,663). A loop on `mut self` whose
    body calls a method is 516 bytes as a `while` loop and 533 as a range loop at `-O s`.
  - **Where it bites:** the walks over a list or a table in fe0 whose bodies make calls, such
    as those in `check.fe`, `codegen.fe` and `lexer.fe`.
  - **Upstream:** we have not reported it.
  - **Workaround:** fe0 walks lists with an index `while` loop (`var k = 0`, then
    `while k < n { …; k += 1 }`).
  - **Remove when:** a release we use builds the six range loops in Back to no more bytes
    than the index loops. Re-measure Back before undoing it.

- **Fe has no cast between a unit-only enum and its variant index.**
  - **Where it bites:** `Tok` in `fe0/src/lexer.fe`. An `enum Tok` makes each phase contract
    larger ([ADR 0014](adr/0014-contract-per-phase.md) gives the figures).
  - **Upstream:** the feature request argotorg/fe#2020 asks for the cast. It is open.
  - **Workaround:** `Tok` is a struct around a `u8`, with a constant per token kind.
  - **Remove when:** a release we use has the cast, and an `enum Tok` then builds each phase
    contract to no more bytes than the struct.
