# Fe0

Fe0 is a small subset of [Fe](https://github.com/argotorg/fe) for writing EVM contracts, with a
compiler written in Fe. It is an entry to the Fe Builders Challenge 2026. The same compiler
runs in three places:
- as a native command line program;
- as EVM bytecode, inside the tests that `fe test` runs;
- on chain, where five contracts on Arbitrum One compile Fe0 source sent in calldata and deploy
  the result: one contract for each compiler phase (Lexer, Parser, Checker, and Back for code
  generation), and Compiler, which calls them in turn ([docs/DEMO.md](docs/DEMO.md)). Two more
  contracts there deploy programs through Compiler and record them with their source
  ([registry/README.md](registry/README.md)).

[docs/SPEC.md](docs/SPEC.md) defines the language, and [docs/DESIGN.md](docs/DESIGN.md)
describes the compiler. Built with **Fe 26.7.0**.

## The problem

Fe has no specification. Its grammar lives in its parser, and its rules live in its type and
effect checker. That makes two things hard: checking a program against a written rule, and
formalizing the language in Lean, which the Fe team wants to do for a subset of it.

## The approach

- **A strict subset.** Fe accepts every program that Fe0 accepts, and runs it the same way. Fe0
  may reject programs that Fe accepts, never the other way round
  ([ADR 0001](docs/adr/0001-strict-subset.md)). SPEC.md states the rule and its two limits:
  gas, and the recursion depth of each build.
- **A written specification.** SPEC.md gives the grammar, the semantics of each expression, and
  the rules for names, types and effects. Each rule marked **[✓]** was confirmed against Fe by
  a probe: a small program that Fe compiles or rejects. The probes are in `spike-*/`,
  `corpus/` and `corpus/reject/`.
- **Tests against Fe itself.** Each corpus program is compiled by Fe and by Fe0. Both builds are
  deployed and sent the same calls. The test checks that the success flags, return data and
  revert data are the same. Storage is compared through later calls that read it. A second
  harness repeats the calls on a local node, from several accounts, and also compares the logs
  and storage writes (DESIGN.md §10). A random program generator adds more programs (DESIGN.md
  §11).
- **Steps toward real contracts.** The corpus goes from a counter to a token and an AMM pool.
  Fe0 programs can read the caller, and use storage maps, events and typed calls to other
  contracts ([ADR 0016](docs/adr/0016-steps-toward-real-contracts.md)).

## Fe's effects

A Fe function declares what it touches in its `uses` clause. A handler that writes a field must
list it as `mut`. This handler, lines 11 to 15 of `corpus/reject/write_without_mut.fe`, does
not. It is the `recv` arm for message `Set`, and `n` is a field of its contract:

```fe
recv M {
    Set { v } uses (n) {
        n = v
    }
}
```

Fe rejects the program. Fe0's CLI, given the file on stdin, rejects it with this error at
line 13 of the file:

```
<stdin>:13:13: E018 field not `mut` in `uses`
```

Fe0 checks Fe's effect rules for storage fields, the caller, logs and external calls (SPEC.md
§6). The compiler also uses effects itself. The `fe0` library reads its source through a
`Source` effect ([ADR 0010](docs/adr/0010-source-effect.md)), so it does no I/O. The native CLI
supplies the source from stdin, the tests from a string, and each phase contract from its
calldata.

## Architecture

```
source ─▶ Lexer ─▶ Parser ─▶ Checker ─▶ Back (code generation, assembly) ─▶ deploy code
```

- `fe0/` is the compiler as a library, with no I/O.
- `fe0-cli/` is the native command line program.
- `fe0-chain/` holds one contract per phase, plus Compiler, which calls each phase in turn.
  The compiler does not fit in one contract under the 24,576-byte limit
  ([ADR 0014](docs/adr/0014-contract-per-phase.md)).
- `registry/` holds two contracts. Registry deploys programs through a listed Compiler and
  records each with its source and the accounts that asked for it. CompilerRegistry holds the
  list of Compilers, which an admin keeps ([ADR 0031](docs/adr/0031-deployment-registry.md),
  [ADR 0034](docs/adr/0034-compiler-registry.md)).
- `corpus/` holds the test programs and their call scripts. `corpus/reject/` holds the programs
  that Fe0 must reject, each with the error it expects. `corpus/gen/` holds the random
  programs that `tools/gen.py` writes. That directory is not in git.
- `tools/` holds the test harnesses and the deployment scripts.

DESIGN.md §1 lists every top-level directory, and §8 gives the size and gas of each
contract of fe0-chain.

## Build and test

Fe 26.7.0 is the reference toolchain ([ADR 0022](docs/adr/0022-move-to-26-7-0.md)). The dev
container (`.devcontainer/`) pins it, together with `uv` for the Python tools. CI runs every
step below in that container (`.github/workflows/ci.yml`).

The unit tests run on the EVM, so they work on every platform:

```sh
(cd fe0 && fe test)
```

The native CLI reads a program on stdin and prints its deploy code as hex. Fe 26.7.0 builds
native code on x86-64 Linux, AArch64 Linux and AArch64 macOS.

```sh
fe build --backend native -e executable --out-dir out/cli fe0-cli
out/cli/fe0_cli < corpus/counter.fe
```

It exits with 0 when the program compiles, 1 when Fe0 rejects it, and 2 on a wrong command
line. Errors and warnings go to stderr as `<stdin>:line:col: CODE message`.

The test harnesses:

| Command | Checks |
|---|---|
| `uv run --project tools tools/embed.py` | each corpus program against Fe, and each reject program's error (DESIGN.md §10) |
| `uv run --project tools tools/gen.py -n 25` | the same, on random programs (DESIGN.md §11) |
| `uv run --project tools tools/cli_check.py` | the native CLI against Fe0 on the EVM, byte for byte |
| `uv run --project tools tools/mutate.py` | the corpus and random programs, each changed by one mutation, against Fe (DESIGN.md §11a) |
| `uv run --project tools tools/node_check.py` | calls from several accounts, logs and storage writes against Fe, on anvil |
| `uv run --project tools tools/chain_check.py` | the on-chain compiler against the native CLI, on anvil |
| `uv run --project tools tools/registry_check.py` | the registry and the compiler list, on anvil; it copies the code of CreateX, a contract factory, from Arbitrum One's public RPC |

No node needs to be running first: the harnesses that use anvil start one. The dev container
installs anvil with Foundry.

## Demo

[docs/DEMO.md](docs/DEMO.md) compiles a program on Arbitrum One for free with an `eth_call`,
shows an error, and deploys a program through the on-chain compiler. `tools/deploy.py
--rehearse` runs the same demo on a local anvil node.

The [playground](https://nikicat.github.io/fe0/) is a web page that does steps 1 to 3 of the
demo ([playground/README.md](playground/README.md)).

## Results

- Every program of `corpus/`, and every random program that the harnesses generate, behaves the
  same under Fe0 and Fe. Every program of `corpus/reject/` gives the error it expects.
- The native CLI, Fe0 on the EVM and the on-chain compiler give the same bytes for every
  program.
- Fe0's output costs more gas than Fe's. Fe0 keeps every local in memory, and Fe keeps them on
  the stack ([ADR 0021](docs/adr/0021-frames-gas-and-depth.md)). Fe0's gas over Fe's
  (`tools/gas_compare.py`, Fe 26.7.0 at optimization level `-O 1`):

  | Kind of program | Fe0 ÷ Fe |
  |---|---|
  | storage-bound, such as `tokens.fe`, `vault.fe`, `escrow.fe` | 1.00 to 1.03 |
  | `amm.fe`, a Uniswap v2–style pair | 1.01 |
  | arithmetic and loops, such as `isqrt`, `power`, `primes` | 1.9 to 3.2 |
  | calls, such as `fib`, `ackermann`, `many_params` | 1.7 to 2.8 |
  | the whole corpus, in total gas | 1.43 |

  Storage costs thousands of gas per access in both builds, so for real contracts the
  difference is a few percent. ADR 0021 plans how to reduce it.

## Limitations

- Fe0 is a subset. The table
  ["Fe0 and Fe at a glance"](docs/SPEC.md#fe0-and-fe-at-a-glance) of SPEC.md shows, feature
  by feature, what Fe0 has, what it has with a narrower rule, and what it leaves out. Among
  what it leaves out: generics, traits, references and memory types.
- Fe0 has only `u256`, `bool` and `Address` as value types. Sized and signed integers are the
  next step of ADR 0016.
- Every contract field must be declared `mut`. Fe also allows a field without `mut`, and keeps
  it out of storage (SPEC.md §6).
- Each phase stops at the first error ([ADR 0006](docs/adr/0006-no-error-recovery.md)).
- Fe0 behaves as Fe does only below the recursion depth of both builds and with enough gas
  (SPEC.md, the subset rule).

## Fe0 as a subset to formalize

The Fe team wants a subset of Fe small enough to formalize in Lean ([docs/PLAN.md](docs/PLAN.md)
§0). Fe0 could be that subset. Fe0 has no Lean model yet. The lists below are what a model could
start from.

By the [subset rule](docs/SPEC.md), Fe accepts every Fe0 program and runs it the same way. So a
theorem about Fe0's programs is a theorem about those Fe programs.

**What keeps a model small.**
- One grammar (SPEC.md §3.1), three value types (SPEC.md §2), and no generics, traits,
  references or memory.
- A name in a body means the innermost declaration of that name (SPEC.md §5.2). No constant
  depends on itself (SPEC.md §5.3).
- SPEC.md §4 fixes the order of every operand, argument, field value and assignment. So the
  semantics is a function: a state and a call give one outcome.
- An outcome is success with return data, or failure with revert data, plus the storage writes
  and logs of a success. SPEC.md §4 and §6 give the revert data of each failure.
- The model takes as inputs the values of the `Ctx` methods, such as the caller (SPEC.md §6),
  and what each external call returns. It may treat `keccak256`, which places map entries and
  names events, as an injective function.
- The subset rule leaves out gas and the builds' recursion limits. So the model needs neither.

**What a model could prove.**
- Type safety: a body that the checker accepts gives a value of its type, or fails with the
  revert data of SPEC.md §4 and §6.
- Effect safety (SPEC.md §6): a body reads, emits and calls only through the
  entries that its `uses` lists, and writes only through the fields that it lists `mut`.
- Free functions are pure (SPEC.md §5.5): their result depends only on their arguments.
- The dispatcher, which routes calldata to the `recv` arms, and `init` decode their input as
  SPEC.md §6 says.
- Fe0's output, or Fe's, runs as the model says. The differential tests of DESIGN.md §10 check
  this on each program of the corpus.

**What is hard to model.** The concrete syntax. The newline rule of SPEC.md §3.4 and the rule
for `<` in SPEC.md §3.2 exist to match Fe's parser. A model can start from the syntax tree, as
the grammar of SPEC.md §3.1 gives it, and leave the parser to the tests.

## Declaration

- **Pre-existing work.** Before the build window (Nov 3 to 24, 2026), on Oct 27 and 28, we wrote
  the plan ([docs/PLAN.md](docs/PLAN.md)), the probe directories `spike-conform/`,
  `spike-deps/`, `spike-keccak/`, `spike-layout/`, `spike-lexer/`, `spike-limits/`,
  `spike-native/` and `spike-spec/`, and the ADRs dated before Nov 3. The last commit before the
  window is `0649397`. Everything after it was written in the window.
- **Reused code.** Fe0 uses only Fe's `core` and `std` libraries. The playground is built
  from npm packages: React, wagmi with [viem](https://viem.sh), TanStack Query and CodeMirror
  ([playground/package.json](playground/package.json)).
- **AI assistance.** Most of the code, tests and docs were written with an AI assistant (Claude
  Code). Each claim about Fe was checked by a probe or a differential test against Fe 26.7.0.

## License

Apache-2.0, see [LICENSE](LICENSE).
