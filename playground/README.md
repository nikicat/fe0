# Playground

A web page for compiling and deploying Fe0 programs with the compiler on chain. Fe0 is a subset
of Fe, the smart contract language ([docs/SPEC.md](../docs/SPEC.md)). Its compiler runs on chain
as five contracts, and the page compiles with the one named Compiler
([docs/DEMO.md](../docs/DEMO.md)). It deploys through the registry, a contract that records
each program it deploys with its source. The page uses the Compiler and the registry on
Arbitrum One, the one chain that `deployments/` records. It is published at
<https://nikicat.github.io/fe0/>.

- **Compile.** The page compiles the program in the editor 0.5 s after each edit, by an
  `eth_call` of Compiler's `compile(bytes)`, so a compile is free and needs no wallet. It
  shows the size of the deploy code and the gas that the compile would cost as a transaction.
  On an error it shows the line, column, code and message, as the command line compiler
  (`fe0-cli`) prints them, and marks the place in the editor.
- **Deploy.** With a browser wallet, the page deploys the program through the registry
  ([registry/README.md](../registry/README.md)). The deploy form takes the parameters of the
  program's `init`, and the page ABI-encodes them as the constructor arguments. The contract's
  address depends only on the compiled program, the arguments and a salt. The form's salt field
  picks the salt ([ADR 0031](../docs/adr/0031-deployment-registry.md), "Deploying"), so any
  text gives a separate instance. The form shows the address before deploying. When a contract
  is already at that address, the form's Deploy button becomes an Open button, which opens the
  contract without deploying. Otherwise Deploy asks the wallet to switch to the page's chain,
  adding it if the wallet lacks it, and sends the transaction from the wallet. The page then
  opens the new contract's page.
- **Registry.** The Registry link in the top bar opens the list of the contracts that the
  registry recorded, newest first, each with the name of the contract in its source and the
  version of the compiler that compiled it. The "Mine" button connects the wallet and lists the
  contracts that its account deployed. A contract's page shows what the registry recorded: that
  version, the constructor arguments, the salt and the source. The page puts the recorded source
  in the editor, and guesses the call forms from it (see Design). For a contract that the
  registry did not record, the forms come from whatever program the editor holds.
- **Call.** A contract's page has a card for each variant of the program's `msg` types. Its Call
  button calls the contract by `eth_call`, which needs no wallet, and its Send button sends a
  transaction from the wallet. The page decodes the return value or the panic. The "Open a
  contract" field, below the Deploy form, opens the page of any address on the page's chain.
- **Share.** "Copy link" puts the program in the link, and opening the link opens that
  program.

The Example menu holds the `.fe` files at the top of `corpus/`, which are the repository's test
programs. A page opened at `#/` starts with the example `corpus/counter.fe`.

## Routes

The route is in the URL's fragment ([ADR 0032](../docs/adr/0032-playground-architecture.md)).

| Fragment | Page |
|---|---|
| `#/` | The editor |
| `#/src/<program>` | The editor, with the program |
| `#/<chain id>/<address>` | The contract at the address |
| `#/<chain id>/<address>/src/<program>` | The contract at the address, with the program in the editor |
| `#/registry` | The registry's contracts |
| `#/registry/<account>` | The contracts that `<account>` deployed |

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
holds what the page needs from the repository. `Config` in `tools/playground.py` lists the
fields of `src/config.ts`, and `src/domain/config.ts` types them.
`.github/workflows/pages.yml` runs the script, builds the page, and publishes `dist/` on each
push to `main`.

The page sends reads to each chain's public RPC endpoint, and transactions to the browser
wallet, which it finds by EIP-6963 or as `window.ethereum`.

## Tests

- `npm test` runs the unit tests with vitest, among them the check of the layer rule of
  ADR 0032.
- `npm run e2e` builds the page and runs its browser tests with Playwright, against an anvil
  fork of the chain that the page opens on (ADR 0032, "Deployment"). It needs `src/config.ts`,
  anvil, Chromium and network access to that chain's RPC endpoint. The dev container has anvil
  and Chromium. Elsewhere, set `CHROMIUM` to the Chromium binary.

## Design

[ADR 0032](../docs/adr/0032-playground-architecture.md) records the stack, the layers of `src/`,
and why the call forms are a guess.
