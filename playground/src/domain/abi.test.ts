import { expect, test } from "vitest";
import { calldata, describeReturn, encodeArgs } from "./abi";
import { type Param, outline } from "./outline";
import type { Source } from "./source";

const o = outline(`msg M {
  #[selector = 0x01] Set { v: u256, to: Address },
  #[selector = 0x02] Get -> u256,
}
contract C { init(a: u256, b: bool) {} }` as Source);

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

test("calldata starts with the selector", () => {
  const [set, get] = o.variants;
  const to = `0x${"ab".repeat(20)}`;
  expect(calldata(set!.selector, filled(set!.fields, ["1", to])))
    .toBe(`0x00000001${word("1")}${word(to.slice(2))}`);
  expect(calldata(get!.selector, [])).toBe("0x00000002");
});

test("describeReturn decodes the return type", () => {
  const get = o.variants[1]!;
  expect(describeReturn(get.returns, `0x${word("5")}`)).toBe("Returned 5");
  expect(describeReturn(null, "0x")).toBe("Returned.");
});
