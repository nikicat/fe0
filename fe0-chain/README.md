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
    // Returns the new contract's address.
    function deploy(bytes calldata src, bytes calldata args) external returns (address);
}
```

The constructor takes the addresses of Lexer, Parser, Checker and Back, in that order.

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
