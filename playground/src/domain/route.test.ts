import { expect, test } from "vitest";
import type { ChainId } from "./config";
import { Route } from "./route";
import type { Source } from "./source";

const address = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266";
const arbitrum = 42161 as ChainId;

test("each route survives its fragment", () => {
  const routes = [
    Route.editor(),
    Route.editor("" as Source),
    Route.editor("// Grüße, 世界 😀\r\nmsg M {}" as Source),
    Route.contract(arbitrum, address),
    Route.contract(arbitrum, address, "msg M {}" as Source),
    Route.registry(),
    Route.registry(address),
  ];
  for (const r of routes) {
    const hash = r.hash();
    expect(hash).toMatch(/^#\/[A-Za-z0-9_=/x-]*$/);
    expect(Route.parse(hash)).toEqual(r);
  }
});

test("a fragment that names no route opens the editor", () => {
  const hashes = ["", "#", "#/", "#/nowhere", "#/src/%%%", "#/42161/0x12", "#/registry/0x12",
    "#/registry/x/y"];
  for (const hash of hashes) {
    expect(Route.parse(hash)).toEqual(Route.editor());
  }
});

test("a route checksums the address that its fragment spells in lowercase", () => {
  const lower = address.toLowerCase();
  expect(Route.parse(`#/42161/${lower}`)).toEqual(Route.contract(arbitrum, address));
  expect(Route.parse(`#/registry/${lower}`)).toEqual(Route.registry(address));
});

test("only a contract's route names a chain", () => {
  expect(Route.contract(arbitrum, address).chainId).toBe(arbitrum);
  expect(Route.editor().chainId).toBeNull();
  expect(Route.registry(address).chainId).toBeNull();
});
