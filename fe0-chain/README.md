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

A deployed Compiler's `version()` returns the version in this ingot's `fe.toml`.
`deployments/<chain id>.json` records each chain's release, with Sourcify's match for each
contract ([ADR 0033](../docs/adr/0033-verify-on-sourcify.md)).

To make a release, raise the version in `fe.toml` and in `version()` in `src/lib.fe`, and
commit. `tools/chain_check.py` fails when the two versions differ. The return type of
`version()` is `String<N>`, where `N` is the length of the version, so a longer or shorter
version needs a new `N` there. Then `tools/deploy.py` deploys the release
([docs/DEMO.md](../docs/DEMO.md), step 4), and `tools/deploy_registry.py` adds its Compiler to
CompilerRegistry ([registry/README.md](../registry/README.md), "Deploy").

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

This builds the contracts as Sourcify rebuilds them, into `out/chain/`
([ADR 0033](../docs/adr/0033-verify-on-sourcify.md)). Then it checks them on a local anvil node
against the native CLI. If `Compiler.abi.json` does not match the build, it fails. Run it with
`--write-abi` to write the file again. `tools/deploy.py` deploys the same build.
