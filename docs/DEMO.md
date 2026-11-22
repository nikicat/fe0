# Demo: the Fe0 compiler on Arbitrum One

Fe0 runs on chain as five contracts. Four of them each run one phase of the compiler, and
Compiler calls them in turn (DESIGN.md §8). `tools/deploy.py` deployed them, and
`deployments/42161.json` records the addresses.

| Contract | Address |
|---|---|
| Compiler | [`0xD7131e490e0194fb306dfE93dfb686081FBCB0b4`](https://arbiscan.io/address/0xD7131e490e0194fb306dfE93dfb686081FBCB0b4) |
| Lexer | [`0xD98A2b13cE4820A4F82fAa17b92066507B353FA6`](https://arbiscan.io/address/0xD98A2b13cE4820A4F82fAa17b92066507B353FA6) |
| Parser | [`0x3568d59585B96366ee9F519E3Fef57f71E7b22A6`](https://arbiscan.io/address/0x3568d59585B96366ee9F519E3Fef57f71E7b22A6) |
| Checker | [`0x6459F8eCA5796E33e9b0ECC76423Ed2fd0e86dcb`](https://arbiscan.io/address/0x6459F8eCA5796E33e9b0ECC76423Ed2fd0e86dcb) |
| Back | [`0xB7d731a2ACD18A2FeAB48963A9C3A41fD080Db57`](https://arbiscan.io/address/0xB7d731a2ACD18A2FeAB48963A9C3A41fD080Db57) |

`fe0-chain/README.md` describes Compiler's interface, its errors and its releases. This call
prints the version of the release that Compiler was built from:

```sh
cast call --rpc-url https://arb1.arbitrum.io/rpc 0xD7131e490e0194fb306dfE93dfb686081FBCB0b4 \
  "version()(string)"
# "0.1.0"
```

## 1. Compile a program, for free

A compile is a read-only `eth_call`, so it needs no wallet and costs nothing. This compiles the
counter of `corpus/counter.fe` on chain and prints its deploy code as hex:

```sh
uv run --project tools tools/compile_on_chain.py corpus/counter.fe
```

The output is the same as the native CLI's (`out/cli/fe0_cli < corpus/counter.fe`), byte for
byte. Without our tools, Foundry's `cast` does the same:

```sh
cast call --rpc-url https://arb1.arbitrum.io/rpc 0xD7131e490e0194fb306dfE93dfb686081FBCB0b4 \
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
arguments `args`. `tools/deploy.py` deployed the counter this way, with start value 2:

- the transaction: [`0x3326fcee…`](https://arbiscan.io/tx/0x3326fceef46210efd34f7641e05949a16c3808ca377f3129cbd12c348fd7e626),
  2,103,265 gas;
- the new contract: [`0x3c673F8AC1120f54443c4DfdEA569FDf37B2EBE0`](https://arbiscan.io/address/0x3c673F8AC1120f54443c4DfdEA569FDf37B2EBE0).

Its `get()` returns 2:

```sh
cast call --rpc-url https://arb1.arbitrum.io/rpc 0x3c673F8AC1120f54443c4DfdEA569FDf37B2EBE0 \
  "get()(uint256)"
```

## 4. Deploy the compiler

`tools/deploy.py --rehearse` deploys the five contracts on a local anvil node and runs this demo
there. Without `--rehearse`, it deploys to Arbitrum One, and only from a release: a commit with
the tag `v<version>` (`fe0-chain/README.md`). Each transaction opens an approval page in the
browser, and the user signs it in their own wallet through `browser-web3-signer`, so no private
key is needed. The five deployments and the demo cost about 16M gas, about 0.0003 ETH at
a gas price of 0.02 gwei.
