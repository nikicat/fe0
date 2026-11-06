# Workarounds for the Fe compiler

Known compiler issues and the shapes we use instead. The toolchain is **Fe 26.5.1**, as
pinned in `.github/workflows/ci.yml`.
Each entry says where it bites, what we do instead, and its upstream status.

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
  default. Use `-O 0` while iterating. CI runs the default level, because that is what
  deploys.

## Open bugs (26.5.1, not checked on master)

Both were found by the random generator (DESIGN.md §11) and are not reported upstream yet.

- **The backend panics on a shift by a large constant.** `x << C` or `x >> C`, where `x` is
  not a constant and `C` is a constant of 2⁶⁴ or more, makes `fe build` and `fe test` panic
  with "Integer overflow when casting to usize" (in `primitive-types`), at every `-O` level.
  `fe check` accepts the program. `1 << C` folds and works.
  - **Reproduction:** `fn h(_ x: u256) -> u256 { x << 0x10000000000000000 }`, called from an
    arm with `h(x)` or `h(5)`.
  - **Workaround:** `Gen.shift_amount` in `tools/gen.py` keeps every shift amount below 512
    outside constant declarations, where the shift folds.
- **`fe fmt` breaks long lines into code that Fe does not parse.** It moves a binary operator
  such as `<` or `<<` to the start of the next line. The parser then rejects that line with
  "line-start `<` is ambiguous" (`1-0001`), even though `fe fmt` exits with 0.
  - **Reproduction:** a `let y: bool = …` whose comparison is longer than the line width.
  - **Workaround:** `tools/embed.py` writes the program modules of its batch ingots without
    formatting them.

## Upstream API churn (master, unreleased)

- **Master removes character I/O from `std::io`** (newsfragment `+native-io.removal`).
  `Read`, `Write`, `read_char`, `write_char`, `host()` and `main(argc, argv)` are gone.
  `Stdout`/`Stdin` effects, `print!` and `StdinReader` replace them.
  - So the compiler core reads its input through **its own `fe0::io::Source` effect**
    ([ADR 0010](adr/0010-source-effect.md)). Only the edge adapters touch std. `fe0` passes
    on both 26.5.1 and master `95ec05413`.
  - The native CLI (`fe0-cli`) is not written yet. It will use 26.5.1's `std::io`, and it
    needs a port to the new API only if we leave 26.5.1.

## Fixed upstream (master only; we stay on 26.5.1)

- **Same-named contracts in two modules** crash codegen (argotorg/fe#1887, fixed by #1890).
  `fe test` fails with `InvalidCodeRegion`, and `fe build` fails with "duplicate root object
  `C` across ingot modules" (`spike-deps/dupname`). The harness still gives every contract a
  unique name (DESIGN.md §10).
- **Native keccak** (argotorg/fe#1886, fixed by #1909). On 26.5.1 the native `Hasher` still
  needs the software keccak (DESIGN.md §12).
- **`enum.extract requires an initialized payload subtree` (IR0600)**, an internal error at
  `-O 1` and above; `-O 0` works. Fixed on master `95ec05413`, probably by its newer Sonatina,
  so it was not reported.
  - **Trigger:** `?` on a `Result<E, T>` inside a `while true` loop, in a function whose own
    `Result` the caller then matches or unwraps. A 46-line reproduction is in
    `spike-harness/ice-min/repro.fe` (git-ignored); run it with `fe test -O 1 repro.fe`.
  - **Workaround on 26.5.1:** `Lexed` and `Ast` carry an `err: Option<Diag>` field instead of
    being a `Result` ([ADR 0011](adr/0011-error-field-not-result.md)).
