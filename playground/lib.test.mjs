// Tests of playground/lib.js.
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";
import {
  charIndex,
  isAddress,
  lineCol,
  lineCount,
  linkFragment,
  linkedSource,
  outline,
  parseValue,
  placeholder,
} from "./lib.js";

const corpus = new URL("../corpus/", import.meta.url);
const read = (name) => readFileSync(new URL(name, corpus), "utf8");

test("outline reads counter's init and variants", () => {
  const o = outline(read("counter.fe"));
  assert.deepEqual(o.init, [{ name: "from", type: "u256", abi: "uint256" }]);
  assert.deepEqual(o.variants.map((v) => [v.name, v.selector, v.returns?.abi ?? null]), [
    ["Increment", "0xd09de08a", null],
    ["Decrement", "0x2baeceb7", null],
    ["Get", "0x6d4ce63c", "uint256"],
    ["Reset", "0xd826f88f", null],
  ]);
});

test("outline skips comments and reads decimal selectors and fields", () => {
  const o = outline(read("doc_comments.fe"));
  const set = o.variants.find((v) => v.name === "Set");
  assert.equal(set.selector, "0x00000001");
  assert.deepEqual(set.fields.map((f) => f.name), ["v", "w"]);
});

test("outline finds a selector for every variant of the corpus", () => {
  const files = readdirSync(corpus).filter((f) => f.endsWith(".fe"));
  for (const f of files) {
    const text = read(f);
    const selectors = text.match(/#\[\s*selector\s*=/g)?.length ?? 0;
    const o = outline(text);
    assert.equal(o.variants.length, selectors, f);
    for (const v of o.variants) {
      assert.ok(v.selector !== null, `${f}: ${v.name}`);
      for (const p of v.fields) assert.ok(p.abi, `${f}: ${v.name}.${p.name}`);
    }
    for (const p of o.init) assert.ok(p.abi, `${f}: init ${p.name}`);
  }
});

test("lineCol counts from 1 and ends lines as fegen.py does", () => {
  assert.deepEqual(lineCol("ab\ncd", 0), { line: 1, col: 1 });
  assert.deepEqual(lineCol("ab\ncd", 4), { line: 2, col: 2 });
  assert.deepEqual(lineCol("a\r\nb", 3), { line: 2, col: 1 });
  assert.deepEqual(lineCol("a\rb", 2), { line: 2, col: 1 });
});

test("lineCount ends lines as lineCol does", () => {
  assert.equal(lineCount(""), 1);
  assert.equal(lineCount("a\nb\r\nc\rd"), 4);
  assert.equal(lineCount("a\n"), 2);
});

test("charIndex turns a byte offset into a UTF-16 index", () => {
  assert.equal(charIndex("ab", 1), 1);
  assert.equal(charIndex("é1", 2), 1);
  assert.equal(charIndex("😀x", 4), 2);
});

test("a share link opens the program it was made from", () => {
  for (const source of ["", "msg M {}", "// Grüße, 世界 😀\r\n"]) {
    const hash = linkFragment(source);
    assert.match(hash, /^#src=[A-Za-z0-9_=-]*$/);
    assert.equal(linkedSource(hash), source);
  }
  assert.equal(linkedSource(""), null);
  assert.equal(linkedSource("#other"), null);
});

test("isAddress takes 20 bytes of hex", () => {
  assert.ok(isAddress(`0x${"aB".repeat(20)}`));
  assert.ok(!isAddress(`0x${"a".repeat(39)}`));
  assert.ok(!isAddress(` 0x${"a".repeat(40)}`));
});

test("parseValue reads each ABI type", () => {
  assert.equal(parseValue("uint256", " 0x10 "), 16n);
  assert.equal(parseValue("bool", "false"), false);
  assert.throws(() => parseValue("uint256", "-1"));
  assert.throws(() => parseValue("uint256", `0x1${"0".repeat(64)}`));
  assert.throws(() => parseValue("address", "0x12"));
  assert.throws(() => parseValue("int8", "1"));
});

test("every Fe0 type with an ABI type has an input", () => {
  const o = outline("contract C { init(a: u256, b: bool, c: Address) {} }");
  for (const p of o.init) assert.notEqual(placeholder(p.abi), "", p.type);
  assert.equal(placeholder("int8"), "");
});
