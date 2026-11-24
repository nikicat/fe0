# 32. The playground is a TypeScript app in layers, built with Vite

- Date: 2026-11-22
- Status: accepted

## Context
The playground (playground/README.md) compiles, deploys and calls Fe0 programs through the
Compiler on chain. When this was decided, it was about 1,000 lines of plain JavaScript
modules with no build step:
- views wrote `innerHTML` directly;
- state lived in the page's elements, such as the target address input and the status line;
- each module found the elements it needed by id;
- only the pure helpers had unit tests.

The next features need many more views and much more shared state: a contract page for each
deployed contract, the list of programs that the registry has deployed and recorded
([0031](0031-deployment-registry.md)), a choice of chain and of compiler, and the contracts that
each account deployed through the registry. Each would add more elements that several modules
read and write.

GitHub Pages serves the page, and `.github/workflows/pages.yml` runs a build step
(`tools/playground.py`) before it publishes, so a build of the page needs no new workflow.

## Decision
The playground becomes a TypeScript app, built by Vite into static files that Pages serves.

**Libraries:**
- React for the views.
- wagmi with viem for wallets and chains. wagmi finds the browser's wallets (EIP-6963),
  switches chains, keeps the account's state and supports several chains at once.
- TanStack Query for reads from the chain. It caches compiles, registry pages and `version()`
  calls, and runs them again when their inputs change. A registry record never changes, so the
  page also keeps each one in the browser's `localStorage`, and a later visit reads it from
  there instead of from the chain.
- CodeMirror 6 for the editor, with Fe0 highlighting and the compile error marked in place.

**Layers.** Each imports only from the layers above it in this table. `src/config.ts`, which
`tools/playground.py` writes (Configuration), is data, so every layer but `domain/` may import
it too, and `domain/` takes what it needs from it as parameters. `src/layers.test.ts` checks
the rule.

| Layer | What it holds | Tests |
|---|---|---|
| `domain/` | Pure functions: a program's bytes and the line and column of an offset (`source.ts`), the outline of a program's `init` and `msg` variants (`outline.ts`), ABI building (`abi.ts`, `values.ts`), revert decoding (`revert.ts`), routes (`route.ts`), the pages of the registry's lists (`registryList.ts`), the salts of the registry's deployments (`salt.ts`), their init code and `CREATE2` addresses through CreateX (`createx.ts`), the search of block headers for a record's block (`search.ts`, `blocks.ts`; ADR 0031, "Reading"), and generic helpers that the standard library lacks (`generic.ts`); and the types of `src/config.ts` (`domain/config.ts`) | Unit tests (vitest) |
| `chain/` | The chains; typed clients for Compiler and the registry, from their ABIs in the repository; and transactions from the wallet | Playwright tests |
| `state/` | Query hooks for chain data (`queries.ts`), the registry's records kept in `localStorage` (`records.ts`), the deploy form's preview (`deployPreview.ts`), the current route, and a small hand-written store for the editor and the forms | Playwright tests |
| `ui/` | Components: the editor, the compile status, the deploy and call forms, the contract page, the registry list and the wallet button | Playwright tests |

The Playwright tests run in CI against an anvil fork of the chain, so they compile and deploy
through the deployed Compiler and registry.

**Routes**, in the URL's fragment, so that they work on Pages:
- `#/`: the editor;
- `#/src/<program>`: a shared program, as its UTF-8 bytes in base64url;
- `#/<chain id>/<address>`: one contract, with its source from the registry, constructor
  arguments, compiler and call forms;
- `#/<chain id>/<address>/src/<program>`: the same, with a shared program;
- `#/registry`: the registry's list, newest first;
- `#/registry/<account>`: the contracts that the account deployed through the registry.

**Configuration.** `tools/playground.py` writes a typed `config.ts` with what the page needs
from the repository, taken from what `deployments/` and `corpus/` record, so the page lists no
chain or contract by hand. `Config` in `tools/playground.py` lists its fields, and
`src/domain/config.ts` types them. A chain whose `block.number` is Ethereum's, as on Arbitrum,
makes the page search block headers for a record's block ([ADR
0031](0031-deployment-registry.md), "Reading").

**Call forms.** The call forms come from an outline of the program, which finds `init` and
the `msg` variants with regular expressions. The page has no Fe0 parser, and the Compiler
returns only deploy code, so nothing gives the page the program's ABI.

**Deployment.** Each page works on one deployment, a chain with its Compiler and registry from
`config.ts`, which the route picks: a contract's route names its chain, and every other route is
on the chain with the lowest id. `config.ts` holds one chain, Arbitrum One, with one Compiler,
so the page has no picker for either until `deployments/` records more. Components and the
hooks of `state/` take it from a React context, not a prop, since leaves such as the transaction
links sit under every panel. The functions and classes of `chain/` take it as an argument, so
they do not depend on React.

**Contract versions.** The page reads the string that a contract's `version()` returns, using
the same signature as Compiler's own `version()` (`fe0-chain/README.md`). It shows that string
on a contract's page when the contract has a `version()`. It also shows the version of the
Compiler that a registry record names, which may be from a different release from the one in
`config.ts`. The page reads `version()` from any contract, so it declares that signature
itself rather than taking it from Compiler's ABI.

The page does not check whether a record's Compiler is listed, since the registry checks that
when it deploys ([0034](0034-compiler-registry.md)).

**Contract pages.** The page deploys through the registry
([0031](0031-deployment-registry.md)), so a contract's page shows the source, constructor
arguments and compiler that the registry recorded, and puts that source in the editor, where
the call forms come from. For a contract that the registry has no record of, the forms come
from whatever program the editor holds, which may not be the contract's.

**Links.** The page links a contract of this repository, such as Compiler or the registry, to
its page on Sourcify, and links no contract to the chain's block explorer. The explorer
verifies no Fe, so it shows only a contract's bytecode, while Sourcify shows the source that it
verified ([0033](0033-verify-on-sourcify.md)). Only transactions link to the explorer.

**Hex values.** The page shortens a long hex value, such as an address or a transaction hash,
with CSS rather than in its text, so that a copy of it gets the whole value.

## Alternatives
- **Keep plain modules and add a small store:** it keeps the page free of a build step, but
  views would still write the page by hand, and nothing would check the types.
- **Svelte or Solid instead of React:** each gives a smaller bundle. React with wagmi is the
  most common stack for a page that talks to wallets, so most help and most examples fit it.
- **Preact and htm from a CDN, with no build:** this gives components without a build step, but
  no types and no wagmi.

## Consequences
- The playground needs Node and npm to build, in CI and on a developer's machine. The dev
  container pins Node, and Pages builds the page in that container, with the same toolchain
  as CI's tests. Pages does not wait for those tests to pass.
- The Playwright tests use Debian's Chromium in the dev container, not the browser that
  Playwright downloads, so the browser gets Debian's security fixes.
- A form that the outline gets wrong sends calldata that the contract does not expect, and the
  contract reverts.

## Open questions
- Whether to compile in the browser: the compiler is EVM code, so a local EVM, such as
  `@ethereumjs/evm`, could run it with no RPC. Only deploying and calling would need a chain.
- Whether a later Compiler release should return the program's ABI, from the types that Fe0's
  checker infers, so that the forms no longer come from the outline. That changes the contracts,
  so it needs a record of its own.
