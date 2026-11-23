import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, test } from "vitest";
import { outline } from "./outline";
import type { Source } from "./source";

const corpus = new URL("../../../corpus/", import.meta.url);
const read = (name: string) => readFileSync(new URL(name, corpus), "utf8") as Source;

describe("outline", () => {
  test("reads counter's init and variants", () => {
    const o = outline(read("counter.fe"));
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
});
