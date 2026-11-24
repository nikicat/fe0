import { expect, test } from "vitest";
import { encodeArgs, tryEncodeArgs } from "./abi";
import type { Param } from "./outline";
import { Program, type Source } from "./source";

const o = new Program("contract C { init(a: u256, b: bool) {} }" as Source).outline();

// Returns each of `params` with the text at the same index.
const filled = (params: readonly Param[], texts: string[]) =>
  params.map((param, i) => ({ param, text: texts[i]! }));

// Returns `hex` padded to a 32-byte word.
const word = (hex: string) => hex.padStart(64, "0");

test("encodeArgs encodes init's parameters, and names the one it cannot read", () => {
  expect(encodeArgs(filled(o.init, ["2", "true"]))).toBe(`0x${word("2")}${word("1")}`);
  expect(() => encodeArgs(filled(o.init, ["x", "true"]))).toThrow(/^a: "x" is not a u256$/);
  expect(encodeArgs([])).toBe("0x");
});

test("tryEncodeArgs keeps the encoding, or the error's message", () => {
  expect(tryEncodeArgs(filled(o.init, ["2", "true"])))
    .toEqual({ args: `0x${word("2")}${word("1")}` });
  expect(tryEncodeArgs(filled(o.init, ["x", "true"])))
    .toEqual({ error: 'a: "x" is not a u256' });
});
