// The editor's words follow SPEC.md §1, which owns them.
import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { StringStream } from "@codemirror/language";
import { fe0Tokens, RESERVED, TYPES } from "./fe0Language";

const spec = readFileSync(new URL("../../../docs/SPEC.md", import.meta.url), "utf8");

test("the keywords are SPEC's reserved words", () => {
  const block = spec.match(/\*\*Reserved words\.\*\*[^]*?```\n([^`]*)```/)![1]!;
  expect([...RESERVED].sort()).toEqual(block.split(/\s+/).filter(Boolean).sort());
});

test("the type names are SPEC's type names", () => {
  const para = spec.match(/\*\*Type names\.\*\*([^]*?)type names, not identifiers/)![1]!;
  const named = [...para.matchAll(/`(\w+)`/g)].map(([, w]) => w!).filter((w) => w !== "i");
  const widths = named.filter((w) => w.startsWith("u")).map((w) => w.slice(1));
  for (const w of [...named, ...widths.map((n) => `i${n}`)]) {
    expect(TYPES.test(w), w).toBe(true);
  }
  for (const w of ["u7", "u24", "i512"]) expect(TYPES.test(w), w).toBe(false);
});

// Each token of one line, as [text, style], without the spaces between them.
function tokens(line: string): [string, string | null][] {
  const stream = new StringStream(line, 2, 2);
  const out: [string, string | null][] = [];
  while (!stream.eol()) {
    stream.start = stream.pos;
    const style = fe0Tokens.token(stream, null);
    if (stream.current().trim()) out.push([stream.current(), style]);
  }
  return out;
}

test("a string holds a // and ends before the code after it", () => {
  expect(tokens('assert!(x, "a // b") // c').filter(([, s]) => s)).toEqual([
    ["assert", "keyword"], ["x", "variableName"], ['"a // b"', "string"], ["// c", "comment"],
  ]);
});

test("integers take SPEC's forms", () => {
  expect(tokens("0X1F 0b1_0 1_000")).toEqual([
    ["0X1F", "number"], ["0b1", "number"], ["_0", "variableName"], ["1_000", "number"],
  ]);
});
