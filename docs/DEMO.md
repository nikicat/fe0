# Demo: the Fe0 compiler on Arbitrum One

Fe0 runs on chain as five contracts. Four of them each run one phase of the compiler, and
Compiler calls them in turn (DESIGN.md §8). `tools/deploy.py` deployed them, and
`deployments/42161.json` records the addresses.

| Contract | Address |
|---|---|
| Compiler | [`0x4956c350E3a9e1FEEcEe0FE904053bD2931703b4`](https://arbiscan.io/address/0x4956c350E3a9e1FEEcEe0FE904053bD2931703b4) |
| Lexer | [`0x821F84a486c458311707e7EEd85b58E9FE2FC2e3`](https://arbiscan.io/address/0x821F84a486c458311707e7EEd85b58E9FE2FC2e3) |
| Parser | [`0x02715221094D53c3ADF8E67559e1a275AcB101Ba`](https://arbiscan.io/address/0x02715221094D53c3ADF8E67559e1a275AcB101Ba) |
| Checker | [`0xa405641a6674b0f2dE5af9fC2d203FB5B1C089fa`](https://arbiscan.io/address/0xa405641a6674b0f2dE5af9fC2d203FB5B1C089fa) |
| Back | [`0xb41576E48ccF1905cD7f81d93918916B8d638a30`](https://arbiscan.io/address/0xb41576E48ccF1905cD7f81d93918916B8d638a30) |

The [playground](https://nikicat.github.io/fe0/) does steps 1 to 3 below in the browser
([playground/README.md](../playground/README.md)).

`fe0-chain/README.md` describes Compiler's interface, its errors and its releases. This call
prints the version of the release that Compiler was built from:

```sh
cast call --rpc-url https://arb1.arbitrum.io/rpc 0x4956c350E3a9e1FEEcEe0FE904053bD2931703b4 \
  "version()(string)"
# "0.1.2"
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
cast call --rpc-url https://arb1.arbitrum.io/rpc 0x4956c350E3a9e1FEEcEe0FE904053bD2931703b4 \
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

- the transaction: [`0x82c90535…`](https://arbiscan.io/tx/0x82c905354dcefaea0ea60435283886a0bd580094ae08833c443047b31f686a52),
  2,103,335 gas;
- the new contract: [`0xD7CFBe5bd425D0aDB78caFb38F959D0583d030f2`](https://arbiscan.io/address/0xD7CFBe5bd425D0aDB78caFb38F959D0583d030f2).

Its `get()` returns 2:

```sh
cast call --rpc-url https://arb1.arbitrum.io/rpc 0xD7CFBe5bd425D0aDB78caFb38F959D0583d030f2 \
  "get()(uint256)"
# 2
```

## 4. Deploy the compiler

`tools/deploy.py --rehearse` deploys the five contracts on a local anvil node and runs this demo
there. Without `--rehearse`, it deploys to Arbitrum One, and only from a release: a commit with
the tag `v<version>` (`fe0-chain/README.md`). It sends two transactions. The first deploys the
five contracts through [Multicall3](https://www.multicall3.com) and
[CreateX](https://github.com/pcaversaccio/createx), so either all five are created or none is
([ADR 0028](adr/0028-one-transaction-deploy.md)). A contract that already has code at its
address is left out, so a run after a full deployment sends only the second transaction. The
second transaction deploys the counter of step 3 through the new Compiler. Each transaction
opens an approval page in the browser, and the user signs it in their own wallet through
`browser-web3-signer`, so the script never sees a private key. The first transaction takes
about 14M gas and the second 2.1M, about 0.0003 ETH in all at a gas price of 0.02 gwei.
