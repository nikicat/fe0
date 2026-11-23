import { expect, test } from "vitest";
import type { ChainId } from "./config";
import { type Route, contractRoute, parseRoute, routeHash } from "./route";
import type { Source } from "./source";

const address = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266";
const arbitrum = 42161 as ChainId;

test("each route survives its fragment", () => {
  const routes: Route[] = [
    { page: "editor", source: null },
    { page: "editor", source: "" as Source },
    { page: "editor", source: "// Grüße, 世界 😀\r\nmsg M {}" as Source },
    contractRoute(arbitrum, address),
    { page: "contract", chainId: arbitrum, address, source: "msg M {}" as Source },
  ];
  for (const r of routes) {
    const hash = routeHash(r);
    expect(hash).toMatch(/^#\/[A-Za-z0-9_=/x-]*$/);
    expect(parseRoute(hash)).toEqual(r);
  }
});

test("a fragment that names no route opens the editor", () => {
  for (const hash of ["", "#", "#/", "#/nowhere", "#/src/%%%", "#/42161/0x12"]) {
    expect(parseRoute(hash)).toEqual({ page: "editor", source: null });
  }
});
