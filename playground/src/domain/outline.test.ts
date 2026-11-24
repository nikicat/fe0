import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, test } from "vitest";
import { encodeAbiParameters } from "viem";
import type { EncodedArgs } from "./abi";
import { Program, type Source } from "./source";

const corpus = new URL("../../../corpus/", import.meta.url);
const read = (name: string) => readFileSync(new URL(name, corpus), "utf8") as Source;
const outline = (source: Source) => new Program(source).outline();
// Returns `hex` padded to a 32-byte word.
const word = (hex: string) => hex.padStart(64, "0");

describe("outline", () => {
  test("reads counter's init and variants", () => {
    const o = outline(read("counter.fe"));
    expect(o.name).toBe("Counter");
    expect(o.init).toEqual([{ name: "from", type: "u256", abi: "uint256" }]);
    expect(o.variants.map((v) => [v.name, v.selector, v.returns?.abi ?? null])).toEqual([
      ["Increment", "0xd09de08a", null],
      ["Decrement", "0x2baeceb7", null],
      ["Get", "0x6d4ce63c", "uint256"],
      ["Reset", "0xd826f88f", null],
    ]);
  });

  test("skips comments and reads decimal selectors and fields", () => {
    const set = outline(read("doc_comments.fe")).variants.find((v) => v.name === "Set");
    expect(set?.selector).toBe("0x00000001");
    expect(set?.fields.map((f) => f.name)).toEqual(["v", "w"]);
  });

  test("finds a selector and ABI types for every variant of the corpus", () => {
    for (const f of readdirSync(corpus).filter((f) => f.endsWith(".fe"))) {
      const text = read(f);
      const o = outline(text);
      expect(o.variants.length, f).toBe(text.match(/#\[\s*selector\s*=/g)?.length ?? 0);
      for (const v of o.variants) {
        expect(v.selector, `${f}: ${v.name}`).not.toBeNull();
        for (const p of v.fields) expect(p.abi, `${f}: ${v.name}.${p.name}`).not.toBeNull();
      }
      for (const p of o.init) expect(p.abi, `${f}: init ${p.name}`).not.toBeNull();
    }
  });

  test("gives a selector that does not fit in 4 bytes no selector", () => {
    const o = outline("msg M { #[selector = 0x100000000] A {} }" as Source);
    expect(o.variants[0]?.selector).toBeNull();
  });

  describe("of a program with an init", () => {
    const o = outline("contract C { init(a: u256, b: bool) {} }" as Source);
    const args = encodeAbiParameters([{ type: "uint256" }, { type: "bool" }],
      [2n, true]) as EncodedArgs;
    // No arguments, and arguments with a byte too many.
    const none = "0x" as EncodedArgs;
    const long = `${args}00` as EncodedArgs;

    test("constructorCall spells the contract's creation as a call", () => {
      expect(o.constructorCall(args)).toBe("C(2, true)");
      expect(o.constructorCall(none)).toBe("C(…)");
      expect(outline("contract C {}" as Source).constructorCall(none)).toBe("C()");
      expect(outline("init(a: u256) {}" as Source).constructorCall(args)).toBeNull();
    });

    test("argsText names each argument, and shows data it cannot read as it is", () => {
      expect(o.argsText(args)).toBe("a = 2, b = true");
      expect(o.argsText(long)).toBe(long);
      expect(o.argsText(none)).toBe(none);
      expect(outline("contract C {}" as Source).argsText(none)).toBe("none");
    });
  });

  describe("of a variant", () => {
    const o = outline(`msg M {
      #[selector = 0x01] Set { v: u256, to: Address },
      #[selector = 0x02] Get -> u256,
    }` as Source);
    const [set, get] = o.variants;

    test("calldata starts with the selector", () => {
      const to = `0x${"ab".repeat(20)}`;
      const texts = set!.fields.map((param, i) => ({ param, text: ["1", to][i]! }));
      expect(set!.calldata(texts)).toBe(`0x00000001${word("1")}${word(to.slice(2))}`);
      expect(get!.calldata([])).toBe("0x00000002");
    });

    test("describeReturn decodes the return type", () => {
      expect(get!.describeReturn(`0x${word("5")}`)).toBe("Returned 5");
      expect(set!.describeReturn("0x")).toBe("Returned.");
    });
  });
});
