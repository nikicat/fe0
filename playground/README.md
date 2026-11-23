# Playground

A web page for compiling and deploying Fe0 programs with the compiler on chain. Fe0 is a subset
of Fe, the smart contract language ([docs/SPEC.md](../docs/SPEC.md)). Its compiler runs on chain
as five contracts, and the page talks to the one named Compiler
([docs/DEMO.md](../docs/DEMO.md)). The page uses the Compiler on Arbitrum One, the one
chain that `deployments/` records. It is published at <https://nikicat.github.io/fe0/>.

- **Compile.** The page compiles the program in the editor 0.5 s after each edit, by an
  `eth_call` of Compiler's `compile(bytes)`, so a compile is free and needs no wallet. It
  shows the size of the deploy code and the gas that the compile would cost as a transaction.
  On an error it shows the line, column, code and message, as the command line compiler
  (`fe0-cli`) prints them, and marks the place in the editor.
- **Deploy.** With a browser wallet, the page sends `deploy(src, args)` to Compiler. The
  form takes the parameters of the program's `init`, and the page ABI-encodes them as `args`.
  The page asks the wallet to switch to the chain, and to add it if the wallet lacks it.
  The wallet pays the deployment's gas in ETH ([docs/DESIGN.md](../docs/DESIGN.md) §8 gives
  the gas). The page then opens the new contract's page.
- **Call.** A contract's page has a form for each variant of the program's `msg` types. The
  form calls the contract by `eth_call`, which needs no wallet, or sends a transaction from the
  wallet. The page decodes the return value or the panic. The "Call a deployed contract" field,
  below the Deploy form, opens the page of any address on that chain.
- **Share.** "Copy link" puts the program in the link, and opening the link opens that
  program.

The Example menu holds the `.fe` files at the top of `corpus/`, which are the repository's test
programs.

## Routes

The route is in the URL's fragment ([ADR 0032](../docs/adr/0032-playground-architecture.md)).

| Fragment | Page |
|---|---|
| `#/` | The editor. A page opened here starts with the example `corpus/counter.fe` |
| `#/src/<program>` | The editor, with the program |
| `#/<chain id>/<address>` | The contract at the address, with call forms from the editor's program, which may not be the contract's |
| `#/<chain id>/<address>/src/<program>` | The same, with the program in the editor |

## Build and run

From the repository's root, with uv and Node 26:

```sh
uv run --project tools tools/playground.py
cd playground
npm ci
npm run dev
```

Then open the URL that Vite prints. `npm run build` writes the page to `playground/dist/`.

`tools/playground.py` writes `src/config.ts`, which git ignores and which the build needs. It
holds what the page needs from the repository, as `Config` in `src/domain/config.ts` types it.
`.github/workflows/pages.yml` runs the script, builds the page, and publishes `dist/` on each
push to `main`.

The page sends reads to each chain's public RPC endpoint, and transactions to the browser
wallet, which it finds by EIP-6963 or as `window.ethereum`.

## Tests

- `npm test` runs the unit tests with vitest, among them the check of the layer rule of
  ADR 0032.
- `npm run e2e` builds the page and runs its browser tests with Playwright, against an anvil
  fork of the first chain in `src/config.ts` (ADR 0032). It needs `src/config.ts`, anvil,
  Chromium and network access to that chain's RPC endpoint. The dev container has anvil and
  Chromium. Elsewhere, set `CHROMIUM` to the Chromium binary.

## Design

[ADR 0032](../docs/adr/0032-playground-architecture.md) records the stack, the layers of `src/`,
and why the call forms are a guess.
