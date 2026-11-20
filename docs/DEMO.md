# Demo: the Fe0 compiler on Arbitrum One

Fe0 runs on chain as five contracts. Four of them each run one phase of the compiler, and
Compiler calls them in turn (DESIGN.md §8). `tools/deploy.py` deployed them, and
`deployments/42161.json` records the addresses.

| Contract | Address |
|---|---|
| Compiler | [`0x6743f90Eb910D670d681635947fD8A63B3397C7B`](https://arbiscan.io/address/0x6743f90Eb910D670d681635947fD8A63B3397C7B) |
| Lexer | [`0xE81863dbaa6Cc6649F9c8B43a19B76cc8D6B1aC1`](https://arbiscan.io/address/0xE81863dbaa6Cc6649F9c8B43a19B76cc8D6B1aC1) |
| Parser | [`0xFf3eeBe9F5deAF46610205Cde6cC5A5132D0A030`](https://arbiscan.io/address/0xFf3eeBe9F5deAF46610205Cde6cC5A5132D0A030) |
| Checker | [`0x6427ceD82919812daF51172E16cc5d1e5705B254`](https://arbiscan.io/address/0x6427ceD82919812daF51172E16cc5d1e5705B254) |
| Back | [`0xF15cEFE0E5890Dc67DD075cc357a1573810C3F10`](https://arbiscan.io/address/0xF15cEFE0E5890Dc67DD075cc357a1573810C3F10) |

`fe0-chain/README.md` describes Compiler's interface and its errors.

## 1. Compile a program, for free

A compile is a read-only `eth_call`, so it needs no wallet and costs nothing. This compiles the
counter of `corpus/counter.fe` on chain and prints its deploy code as hex:

```sh
uv run --project tools tools/compile_on_chain.py corpus/counter.fe
```

The output is the same as the native CLI's (`out/cli/fe0_cli < corpus/counter.fe`), byte for
byte. Without our tools, Foundry's `cast` does the same:

```sh
cast call --rpc-url https://arb1.arbitrum.io/rpc 0x6743f90Eb910D670d681635947fD8A63B3397C7B \
  "compile(bytes)(bytes)" "$(cast from-utf8 "$(cat corpus/counter.fe)")"
```

## 2. See an error

A program with an error makes Compiler revert with `CompileError(code, offset)`. The script
prints it as the CLI does:

```sh
uv run --project tools tools/compile_on_chain.py corpus/reject/assign_let.fe
# corpus/reject/assign_let.fe:5:5: N014 cannot assign to this name
```

With `cast`, the revert data holds the two numbers. Code 3014 is `N014`, and offset 101 is
line 5, column 5.

## 3. Deploy a program through Compiler

`deploy(bytes src, bytes args)` compiles the source and deploys it with the constructor
arguments `args`. The demo deployed the counter with start value 2:

- the transaction: [`0xdb6f7b7e…`](https://arbiscan.io/tx/0xdb6f7b7e76451807757c88886e5c37462a7633a5309d63efaa474379a8e16044),
  2,125,480 gas;
- the new contract: [`0xd34823a55Cae65c980e3535a992e2c23505b858F`](https://arbiscan.io/address/0xd34823a55Cae65c980e3535a992e2c23505b858F).

Its `get()` returns 2:

```sh
cast call --rpc-url https://arb1.arbitrum.io/rpc 0xd34823a55Cae65c980e3535a992e2c23505b858F \
  "get()(uint256)"
```

## 4. Run it all again

`tools/deploy.py --rehearse` deploys the five contracts on a local anvil node and runs this
demo there. Without `--rehearse`, it deploys to Arbitrum One. Each transaction opens an
approval page in the browser, and the user signs it in their own wallet through
`browser-web3-signer`, so no private key is needed. The five deployments and the demo cost
about 18M gas, about 0.0004 ETH at Arbitrum's 0.02 gwei.
