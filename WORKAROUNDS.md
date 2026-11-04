# Workarounds for the Fe compiler

Known compiler issues and the shapes we use instead. The toolchain is **Fe 26.5.1**, as
pinned in `.github/workflows/ci.yml`.
Each entry says where it bites, what we do instead, and its upstream status.

## Open

### `enum.extract requires an initialized payload subtree` (IR0600)

- **Symptom:** `fe test` fails with `internal error: error [IR0600] enum.extract requires an
  initialized payload subtree @ …(%lex_text, enum.extract)`.
- **When:** a test helper extracted the `Ok` payload of the lexer's `Result<Diag, Lexed>`, with
  either `unwrap()` or `match`. The helper ran `lex()` inside `with (Read = …)`, before fe0's
  own `Source` effect replaced `Read`. In the failing version, `Lexed` held two `MemVec`s.
  - A smaller program does not reproduce it. That program builds a `Result<E, S>` whose `S`
    holds a `MemVec<u8>` and a `MemVec` of a `Copy` struct, in a loop that uses `?` inside
    `with` (`spike-harness/ice`, git-ignored).
- **Only with optimizations:** the original `Result` version compiles and runs at `-O 0`. It
  fails at `-O 1` and at the default level (`spike-harness/ice-lexer`, git-ignored).
- **Workaround:** `lex()` returns `Lexed` with an `err: Option<Diag>` field instead of a
  `Result`.
- **Upstream:** not yet reported. The failing version is saved for a reproduction. Minimize it
  and check it on master first.

## Language idioms (not bugs, but they cost time)

- `var` declares a mutable local.
- Fe has no `loop`, so write `while true`.
- `as` only allows provably lossless casts. `i32 → u256` needs `.downcast_truncate()`, and so
  does `usize → u64` (because `usize` is 256-bit on the EVM).
- A shift amount must have the same type as the shifted value.
- `MemVec[i]` yields an access, so bind a non-`Copy` element with `let x = ref v[i]`.
- `MemVec` has no `span()`. Use `.into_array().span()` instead.
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

## Upstream API churn (master, unreleased)

- **Master removes character I/O from `std::io`** (newsfragment `+native-io.removal`).
  `Read`, `Write`, `read_char`, `write_char`, `host()` and `main(argc, argv)` are gone.
  `Stdout`/`Stdin` effects, `print!` and `StdinReader` replace them.
  - So the compiler core reads its input through **its own `fe0::io::Source` effect**. Only
    the edge adapters touch std. `fe0` passes on both 26.5.1 and master `95ec05413`.
  - The native CLI (`fe0-cli`) is not written yet. It will use 26.5.1's `std::io`, and it
    needs a port to the new API only if we leave 26.5.1.

## Fixed upstream (master only; we stay on 26.5.1)

- **Same-named contracts in two modules** crash codegen (argotorg/fe#1887, fixed by #1890).
  `fe test` fails with `InvalidCodeRegion`, and `fe build` fails with "duplicate root object
  `C` across ingot modules" (`spike-deps/dupname`). The harness still gives every contract a
  unique name (DESIGN.md §10).
- **Native keccak** (argotorg/fe#1886, fixed by #1909). On 26.5.1 the native `Hasher` still
  needs the software keccak (DESIGN.md §12).
