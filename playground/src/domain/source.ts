// The text of a Fe0 program (tools/fegen.py, `FeSource`).
export type Source = string & { readonly __brand: "Source" };

// A byte offset in a program's UTF-8 source, as `CompileError` holds it.
export type ByteOffset = number & { readonly __brand: "ByteOffset" };

// A line and a column, both from 1. The column counts bytes, as the native CLI does.
export interface LineCol {
  line: number;
  col: number;
}

// Returns the line and column of `offset` in `source`. Lines end at `\n`, `\r\n` or `\r`, as in
// tools/fegen.py's `LineCol.of`.
export function lineCol(source: Source, offset: ByteOffset): LineCol {
  const bytes = new TextEncoder().encode(source);
  let line = 1;
  let start = 0;
  for (let i = 0; i < Math.min(offset, bytes.length); i++) {
    if (bytes[i] === 0x0a || (bytes[i] === 0x0d && bytes[i + 1] !== 0x0a)) {
      line++;
      start = i + 1;
    }
  }
  return { line, col: offset - start + 1 };
}

// A range of UTF-16 indexes in a program's source, as CodeMirror takes it.
export interface CharRange {
  from: number;
  to: number;
}

// Returns the range of the character at `offset` in `source`, which is empty at its end.
export function charRange(source: Source, offset: ByteOffset): CharRange {
  const before = new TextEncoder().encode(source).slice(0, offset);
  const from = new TextDecoder().decode(before).length;
  const point = source.codePointAt(from);
  return { from, to: from + (point === undefined ? 0 : String.fromCodePoint(point).length) };
}
