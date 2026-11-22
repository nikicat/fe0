# 32. The playground is a TypeScript app in layers, built with Vite

- Date: 2026-11-22
- Status: proposed

## Context
The playground (playground/README.md) compiles, deploys and calls Fe0 programs through the
Compiler on chain. It is about 1,000 lines of plain JavaScript modules with no build step:
- views write `innerHTML` directly;
- state lives in the page's elements, such as the target address input and the status line;
- each module finds the elements it needs by id;
- only `lib.js` has unit tests.

The next features need far more of it: a contract page for each deployed contract, the
registry's list ([0031](0031-deployment-registry.md)), a choice of chain and of compiler, and
labels. Each would add more elements that several modules read and write.

GitHub Pages serves the page, and `.github/workflows/pages.yml` already runs a build step
(`tools/playground.py`) before it publishes.

## Decision
The playground becomes a TypeScript app, built by Vite into static files that Pages serves.

**Libraries:**
- React for the views.
- wagmi with viem for wallets and chains. wagmi finds the browser's wallets (EIP-6963),
  switches chains, keeps the account's state and supports several chains at once.
- TanStack Query for reads from the chain. It caches compiles, registry pages and `version()`
  calls, and runs them again when their inputs change.
- CodeMirror 6 for the editor, with Fe0 highlighting and the compile error marked in place.

**Layers.** Each depends only on the layers above it:

| Layer | What it holds | Tests |
|---|---|---|
| `domain/` | Pure functions: the outline of a program's `init` and `msg` variants, ABI building, revert decoding, salts and `CREATE2` addresses | Unit tests (vitest) |
| `chain/` | Typed clients for Compiler and the registry, from the committed ABIs, and the chains | Tests against anvil |
| `state/` | Query hooks for chain data, and a small store for the editor and the forms | |
| `ui/` | Components: the editor, the compile status, the deploy and call forms, the contract page, the registry list, the chain picker and the wallet button | Playwright tests in CI, against an anvil fork |

**Routes**, in the URL's fragment, so that they work on Pages:
- `#/`: the editor;
- `#/<chain>/<address>`: one contract, with its source, labels, constructor arguments,
  compiler and call forms;
- `#/registry`: the registry's list, which can be filtered by deployer or compiler;
- `#/src/<base64>`: a shared program.

**Configuration.** `tools/playground.py` writes a typed `config.ts` from `deployments/*.json`:
each chain, its Compiler and registry addresses, and the release tag of each known Compiler.
The registry's client marks the compilers in that list as known.

## Alternatives
- **Keep plain modules and add a small store:** it keeps the page free of a build step, but
  views would still write the page by hand, and nothing would check the types.
- **Svelte or Solid instead of React:** each gives a smaller bundle. React with wagmi is the
  most common stack for a page that talks to wallets, so most help and most examples fit it.
- **Preact and htm from a CDN, with no build:** this gives components without a build step, but
  no types and no wagmi.

## Consequences
- The playground needs Node and npm to build, in CI and on a developer's machine.
- `tools/playground.py` writes the configuration only; Vite builds the page.
- `playground/lib.js` and its tests move into `domain/` as TypeScript.
- The call forms still come from the outline, which reads the source with regular expressions
  and can be wrong (playground/README.md, "Design").

## Open questions
- Whether to compile in the browser: the compiler is EVM code, so a local EVM, such as
  `@ethereumjs/evm`, could run it with no RPC. Only deploying and calling would need a chain.
- Whether a later Compiler release should return the program's ABI, from the checker's types,
  so that the forms no longer come from the outline. That changes the contracts, so it needs a
  record of its own.
