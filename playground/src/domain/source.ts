import { type Hex, bytesToHex, hexToString } from "viem";
import { Outline } from "./outline";

// The text of a Fe0 program (tools/fegen.py, `FeSource`).
export type Source = string & { readonly __brand: "Source" };

// A byte offset in a program's UTF-8 source, as `CompileError` holds it.
export type ByteOffset = number & { readonly __brand: "ByteOffset" };

// A line and a column, both from 1. The column counts bytes, as the native CLI does.
export interface LineCol {
  line: number;
  col: number;
}

// A range of UTF-16 indexes in a program's source, as CodeMirror takes it.
export interface CharRange {
  from: number;
  to: number;
}

// A Fe0 program, with the UTF-8 bytes of its source, in which a `ByteOffset` counts.
export class Program {
  readonly source: Source;
  readonly #utf8: Uint8Array;
  #outline: Outline | undefined;

  constructor(source: Source) {
    this.source = source;
    this.#utf8 = new TextEncoder().encode(source);
  }

  // Returns the program whose UTF-8 bytes are `bytes`.
  static fromBytes(bytes: Hex): Program {
    return new Program(hexToString(bytes) as Source);
  }

  // Returns the program's UTF-8 bytes, which is how a program travels on chain.
  bytes(): Hex {
    return bytesToHex(this.#utf8);
  }

  // Returns the program's outline, found on the first call.
  outline(): Outline {
    return this.#outline ??= Outline.of(this.source);
  }

  // Returns the line and column of `offset`. Lines end at `\n`, `\r\n` or `\r`, as in
  // tools/fegen.py's `LineCol.of`.
  lineCol(offset: ByteOffset): LineCol {
    const bytes = this.#utf8;
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

  // Returns the range of the character at `offset`, which is empty at the program's end.
  charRange(offset: ByteOffset): CharRange {
    const from = new TextDecoder().decode(this.#utf8.subarray(0, offset)).length;
    const point = this.source.codePointAt(from);
    return { from, to: from + (point === undefined ? 0 : String.fromCodePoint(point).length) };
  }
}
