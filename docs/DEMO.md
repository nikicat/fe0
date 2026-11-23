# Demo: the Fe0 compiler on Arbitrum One

Fe0 runs on chain as five contracts. Four of them each run one phase of the compiler, and the
fifth, Compiler, calls them in turn ([DESIGN.md](DESIGN.md) §8).
[`tools/deploy.py`](../tools/deploy.py) deployed them, and
[`deployments/42161.json`](../deployments/42161.json) records their addresses and Sourcify's
matches (42161 is Arbitrum One's chain id). The [playground](https://nikicat.github.io/fe0/)
does steps 1 to 3 below in the browser, and links Compiler to its page on Sourcify, which
verified its source ([ADR 0033](adr/0033-verify-on-sourcify.md)).

Before the `cast` commands below, set `COMPILER` to Compiler's address in
`deployments/42161.json`.

[`fe0-chain/README.md`](../fe0-chain/README.md) describes Compiler's interface, its errors and
its releases. This call prints the version of the release that Compiler was built from:

```sh
cast call --rpc-url https://arb1.arbitrum.io/rpc "$COMPILER" "version()(string)"
```

## 1. Compile a program, for free

A compile is a read-only `eth_call`, so it needs no wallet and costs nothing. This compiles the
counter of [`corpus/counter.fe`](../corpus/counter.fe) on chain and prints its deploy code as
hex:

```sh
uv run --project tools tools/compile_on_chain.py corpus/counter.fe
```

The output is the same as the native CLI's (`out/cli/fe0_cli < corpus/counter.fe`), byte for
byte. Without our tools, Foundry's `cast` does the same:

```sh
cast call --rpc-url https://arb1.arbitrum.io/rpc "$COMPILER" \
  "compile(bytes)(bytes)" "$(cast from-utf8 "$(cat corpus/counter.fe)")"
```

## 2. See an error

A program with an error makes Compiler revert with `CompileError(code, offset)`. The script
prints it as the CLI does:

```sh
uv run --project tools tools/compile_on_chain.py corpus/reject/assign_let.fe
# corpus/reject/assign_let.fe:5:5: N014 cannot assign to this name
```

With `cast`, the revert data holds the two numbers. Code 3014 is `N014` ([`fe0-chain/README.md`,
"Errors"](../fe0-chain/README.md#errors)), and byte offset 101 is line 5, column 5.

## 3. Deploy a program through Compiler

`deploy(bytes src, bytes args)` compiles the source and deploys it with the constructor
arguments `args`. [`tools/deploy.py`](../tools/deploy.py) deploys the counter this way, with
start value 2, and prints the new contract's address. With that address in `COUNTER`, its
`get()` returns 2:

```sh
cast call --rpc-url https://arb1.arbitrum.io/rpc "$COUNTER" "get()(uint256)"
# 2
```

## 4. Deploy the compiler

[`tools/deploy.py`](../tools/deploy.py) deploys the five contracts to Arbitrum One and runs this
demo there, and `--rehearse` does the same on a local anvil node. `tools/deploy.py --help` says
what it sends, verifies and records, and how the user signs each transaction in their own wallet
through [`browser-web3-signer`](https://github.com/nikicat/browser-web3-signer). Deploying them
costs about 0.0003 ETH at a gas price of 0.02 gwei ([DESIGN.md](DESIGN.md) §8 gives the gas).

## 5. The registry

Registry deploys a program through a Compiler that CompilerRegistry lists, and records it with
its source ([ADR 0031](adr/0031-deployment-registry.md)). CompilerRegistry lists the Compiler
above. [`registry/README.md`](../registry/README.md) gives the addresses of both on Arbitrum
One, under "Deployed", and how they were deployed, under "Deploy".
