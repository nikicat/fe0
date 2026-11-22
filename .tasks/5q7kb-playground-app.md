---
status: todo
deps: [T0010]
tags: [playground]
---
# Rebuild the playground as a TypeScript app

## Goal
Rebuild `playground/` as the TypeScript app that ADR 0032 describes: Vite, React, wagmi with
viem, TanStack Query and CodeMirror 6, in the layers `domain/`, `chain/`, `state/` and `ui/`,
with routes in the URL's fragment. Done means:
- the page does everything it does now (compile, show an error, deploy, call, share a link);
- it has a contract page at `#/<chain>/<address>`;
- `.github/workflows/pages.yml` builds and publishes it;
- CI runs its unit tests and its Playwright tests against an anvil fork.

The registry's list and labels (ADR 0031) come once the registry exists.

## Decisions
- The stack and the layers are ADR 0032's. It is still "proposed"; mark it accepted when the
  work starts.
- Start after the submission (T0010), since the page in `playground/` works with v0.1.2.

## Next
Set up Vite and TypeScript in `playground/`, and port `lib.js` and its tests to `domain/`.
