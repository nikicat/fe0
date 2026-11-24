import { expect, test } from "vitest";
import { type ByteOffset, Program, type Source } from "./source";

const program = (text: string) => new Program(text as Source);

test("lineCol counts from 1 and ends lines as fegen.py does", () => {
  expect(program("ab\ncd").lineCol(0 as ByteOffset)).toEqual({ line: 1, col: 1 });
  expect(program("ab\ncd").lineCol(4 as ByteOffset)).toEqual({ line: 2, col: 2 });
  expect(program("a\r\nb").lineCol(3 as ByteOffset)).toEqual({ line: 2, col: 1 });
  expect(program("a\rb").lineCol(2 as ByteOffset)).toEqual({ line: 2, col: 1 });
});

test("charRange turns a byte offset into the UTF-16 range of its character", () => {
  expect(program("ab").charRange(1 as ByteOffset)).toEqual({ from: 1, to: 2 });
  expect(program("é1").charRange(2 as ByteOffset)).toEqual({ from: 1, to: 2 });
  expect(program("😀x").charRange(4 as ByteOffset)).toEqual({ from: 2, to: 3 });
  expect(program("a😀").charRange(1 as ByteOffset)).toEqual({ from: 1, to: 3 });
  expect(program("ab").charRange(2 as ByteOffset)).toEqual({ from: 2, to: 2 });
});

test("bytes encodes UTF-8 and fromBytes decodes it", () => {
  const p = program("fn é() {}");
  expect(p.bytes()).toBe("0x666e20c3a92829207b7d");
  expect(Program.fromBytes(p.bytes()).source).toBe(p.source);
});

test("outline is found once", () => {
  const p = program("contract C {}");
  expect(p.outline().name).toBe("C");
  expect(p.outline()).toBe(p.outline());
});
