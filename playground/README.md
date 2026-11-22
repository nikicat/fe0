# Playground

A web page for compiling and deploying Fe0 programs with the compiler on Arbitrum One. Fe0 is
a subset of Fe, the smart contract language ([docs/SPEC.md](../docs/SPEC.md)). Its compiler
runs on chain as five contracts, and the page talks to the one named Compiler
([docs/DEMO.md](../docs/DEMO.md)). It is published at <https://nikicat.github.io/fe-contest/>.

- **Compile.** The page compiles the program in the editor 0.5 s after each edit, by an
  `eth_call` of Compiler's `compile(bytes)`, so a compile is free and needs no wallet. It
  shows the size of the deploy code and the gas that the compile used. On an error it shows
  the line, column, code and message, as the command line compiler (`fe0-cli`) prints them.
- **Deploy.** With a browser wallet, the page sends `deploy(src, args)` to Compiler. The
  form takes the parameters of the program's `init`, and the page ABI-encodes them as `args`.
  The page asks the wallet to switch to Arbitrum One, and to add it if the wallet lacks it.
  Deploying `corpus/counter.fe` takes about 2.1M gas ([docs/DESIGN.md](../docs/DESIGN.md) §8),
  paid in ETH on Arbitrum One.
- **Call.** Each variant of the program's `msg` types gets a form. The form calls a contract by
  `eth_call`, or sends a transaction from the wallet. The contract is the one the page deployed,
  or any address you enter. The page decodes the return value or the panic.
- **Share.** "Copy link" puts the program in the link's fragment, as base64, and opening the
  link opens that program.

The Example menu holds the `.fe` files directly in `corpus/`, the test programs of the
repository. Deploying and sending need a browser wallet. Compiling and calling do not.

## Build and run

From the repository's root, with uv and, for the tests, Node 22:

```sh
uv run --project tools tools/playground.py
python3 -m http.server -d out/playground
```

Then open <http://localhost:8000/>.

`tools/playground.py` copies the page into `out/playground/` and writes `data.json` there. That
file holds what the page needs from the repository: the chain, Compiler's address, release and
interface, the CLI's message for each error code, and the examples.
`.github/workflows/pages.yml` runs the same script and publishes the directory on each push to
`main`.

The page loads [viem](https://viem.sh) from jsDelivr. It sends calls to Arbitrum's public RPC
endpoint, and transactions to the browser wallet (EIP-1193).

`node --test playground/*.test.mjs` runs the tests of `lib.js`.

## Design

- **The forms are a guess.** `outline` in `lib.js` finds `init` and the `msg` variants with
  regular expressions. The page has no Fe0 parser, and the compiler on chain
  returns only deploy code. A form that the guess gets wrong sends calldata that the contract
  does not expect, and the contract reverts.
