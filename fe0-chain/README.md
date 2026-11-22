# fe0-chain: the Fe0 compiler on chain

Compiler compiles Fe0 source sent in calldata. It calls one contract per compiler phase:
Lexer, Parser, Checker and Back (docs/DESIGN.md §8).

## Interface

`Compiler.abi.json` is Compiler's ABI. In Solidity terms:

```solidity
interface ICompiler {
    // A phase found an error in the source.
    error CompileError(uint256 code, uint256 offset);

    // Returns the deploy code of `src`. Call it with eth_call: it changes nothing.
    function compile(bytes calldata src) external view returns (bytes memory);

    // Compiles `src`, appends `args` to the deploy code and deploys it with CREATE.
    // `args` is the ABI encoding of the program's `init` arguments, or empty.
    // Returns the new contract's address. Errors with the init code's revert data when
    // CREATE creates no contract. The data is empty when the init code did not revert, such
    // as when it ran out of gas or returned runtime code over 24,576 bytes (EIP-170).
    function deploy(bytes calldata src, bytes calldata args) external returns (address);

    // Returns the version of the release that this Compiler was built from, such as "0.1.0".
    function version() external pure returns (string memory);
}
```

The constructor takes the addresses of Lexer, Parser, Checker and Back, in that order.

## Releases

A release is a commit that has the git tag `v<version>`, where the version is the one in this
ingot's `fe.toml`. A deployed Compiler's `version()` returns that version, so its tag gives the
commit that Compiler was built from. `tools/deploy.py` refuses to deploy any other commit to a
real chain, and records the version and the commit in `deployments/<chain id>.json`.

To make a release, raise the version in `fe.toml` and in `version()` in `src/lib.fe`, commit,
and tag the commit. `tools/chain_check.py` fails when the two versions differ. The return type
of `version()` is `String<N>`, where `N` is the length of the version, so a longer or shorter
version needs a new `N` there.

## Errors

On an error in the source, `compile` and `deploy` revert with `CompileError`.

- **`code`:** the error's code as a number. The thousands give the phase, and the rest give
  the number within it. So 6034 is `C034`.

  | Thousands | Letter | Phase |
  |---|---|---|
  | 1 | `L` | lexer |
  | 2 | `P` | parser |
  | 3 | `N` | names |
  | 4 | `T` | types |
  | 5 | `E` | effects |
  | 6 | `C` | constants |
  | 7 | `G` | generation |

  The codes are listed in `fe0/src/diag.fe`. Their messages are in
  `fe0-cli/src/messages.fe`.
- **`offset`:** the byte offset in `src` that the error points to.

Only the first error is reported. Warnings, such as an unused `uses` entry, are not.

## Build and check

```sh
uv run --project tools tools/chain_check.py
```

This builds the contracts at `-O s` into `out/chain/`. Then it checks them on a local anvil
node against the native CLI. If `Compiler.abi.json` no longer matches the build, it fails.
Run it with `--write-abi` to write the file again.
