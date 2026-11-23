import { expect, test } from "vitest";
import { type ByteOffset, type Source, charRange, lineCol } from "./source";

test("lineCol counts from 1 and ends lines as fegen.py does", () => {
  expect(lineCol("ab\ncd" as Source, 0 as ByteOffset)).toEqual({ line: 1, col: 1 });
  expect(lineCol("ab\ncd" as Source, 4 as ByteOffset)).toEqual({ line: 2, col: 2 });
  expect(lineCol("a\r\nb" as Source, 3 as ByteOffset)).toEqual({ line: 2, col: 1 });
  expect(lineCol("a\rb" as Source, 2 as ByteOffset)).toEqual({ line: 2, col: 1 });
});

test("charRange turns a byte offset into the UTF-16 range of its character", () => {
  expect(charRange("ab" as Source, 1 as ByteOffset)).toEqual({ from: 1, to: 2 });
  expect(charRange("é1" as Source, 2 as ByteOffset)).toEqual({ from: 1, to: 2 });
  expect(charRange("😀x" as Source, 4 as ByteOffset)).toEqual({ from: 2, to: 3 });
  expect(charRange("a😀" as Source, 1 as ByteOffset)).toEqual({ from: 1, to: 3 });
  expect(charRange("ab" as Source, 2 as ByteOffset)).toEqual({ from: 2, to: 2 });
});
