---
status: doing
deps: [T0010]
tags: [playground]
---
# Rebuild the playground as a TypeScript app

## Goal
Rebuild `playground/` as the TypeScript app that ADR 0032 describes: Vite, React, wagmi with
viem, TanStack Query and CodeMirror 6, in the layers `domain/`, `chain/`, `state/` and `ui/`,
with routes in the URL's fragment. Done means:
- the page compiles, shows an error, deploys, calls and shares a link;
- it has a contract page at `#/<chain>/<address>`;
- `.github/workflows/pages.yml` builds and publishes it;
- CI runs its unit tests and its Playwright tests against an anvil fork.

The registry's list and labels (ADR 0031) come once the registry exists.

## Decisions
- The stack and the layers are ADR 0032's.
- The store is a few lines over `useSyncExternalStore`, not a library.
- The Playwright tests use Debian's Chromium, which the Containerfile installs, and send the
  page's RPC requests to an anvil fork through `page.route`, so the page has no test-only
  setting.
- Packages were installed with `npm install --before=2026-11-08`, so each is at least two
  weeks old.

## State
Committed on `main`, not pushed. An /unsmell run reviewed the rewrite; its record is in
`.git/unsmell/20261123-001647/`. Locally: `npm test` (30 tests), `tsc -b`, `vite build` and
`npm run e2e` (5 tests against a fork of Arbitrum One) pass, on Node 22 and on Node 26.13.1.
CI has not run it: the dev container image must be rebuilt, with Chromium and Node 26.

## Next
Push, and check the "playground" group of CI and the Pages build. Then close this
task.

## Plan from /unsmell (run 20261123-001647)
- `.github/workflows/pages.yml`: Pages publishes each push to `main` without waiting for CI,
  so a page that fails its tests is still published. Fix: run Pages on `workflow_run` of CI
  with a success condition, or make the publish a job of CI that needs the test job.
- `README.md` (root): some unchanged lines run over 96 columns (for example line 32). Rewrap
  them when that file is next edited.
