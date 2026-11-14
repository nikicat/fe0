# Demo: the Fe0 compiler on Arbitrum One

Fe0 runs on chain as five contracts. Four of them each run one phase of the compiler, and
Compiler calls them in turn (DESIGN.md §8). They were deployed on Nov 14, 2026, with
`tools/deploy.py`. `deployments/42161.json` records the addresses.

| Contract | Address |
|---|---|
| Compiler | [`0xc3166Af5e42019C1f986b2e1f4958D69C377fe79`](https://arbiscan.io/address/0xc3166Af5e42019C1f986b2e1f4958D69C377fe79) |
| Lexer | [`0x706d715692f1ECF1A26171a43Ed476DF81A38441`](https://arbiscan.io/address/0x706d715692f1ECF1A26171a43Ed476DF81A38441) |
| Parser | [`0x57ca98785024010E16e3487611dBfD8a895505D7`](https://arbiscan.io/address/0x57ca98785024010E16e3487611dBfD8a895505D7) |
| Checker | [`0xd36E74A23bFf124b891CfD1E0AB738bc1bc1e342`](https://arbiscan.io/address/0xd36E74A23bFf124b891CfD1E0AB738bc1bc1e342) |
| Back | [`0x5A21bf7093de315B284251398E59b2C88B73cb8d`](https://arbiscan.io/address/0x5A21bf7093de315B284251398E59b2C88B73cb8d) |

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
cast call --rpc-url https://arb1.arbitrum.io/rpc 0xc3166Af5e42019C1f986b2e1f4958D69C377fe79 \
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

- the transaction: [`0xec990daa…`](https://arbiscan.io/tx/0xec990daa3b796b174cfab6c56f418f15c953f8974f1bd6e0b5885a15b6be5212),
  2,415,927 gas;
- the new contract: [`0x58307ED5Db3E1F9EdCe546258Cbf2d23fBA89F57`](https://arbiscan.io/address/0x58307ED5Db3E1F9EdCe546258Cbf2d23fBA89F57).

Its `get()` returns 2:

```sh
cast call --rpc-url https://arb1.arbitrum.io/rpc 0x58307ED5Db3E1F9EdCe546258Cbf2d23fBA89F57 \
  "get()(uint256)"
```

## 4. Run it all again

`tools/deploy.py --rehearse` deploys the five contracts on a local anvil node and runs this
demo there. Without `--rehearse`, it deploys to Arbitrum One. Each transaction opens an
approval page in the browser, and the user signs it in their own wallet through
`browser-web3-signer`, so no private key is needed. The five deployments and the demo cost
about 18M gas, about 0.0004 ETH at Arbitrum's 0.02 gwei.
