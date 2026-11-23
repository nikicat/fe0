// Highlighting of Fe0 for CodeMirror, by the words of SPEC.md §1, which fe0Language.test.ts
// checks against SPEC.md.
import { HighlightStyle, StreamLanguage, type StreamParser } from "@codemirror/language";
import { tags } from "@lezer/highlight";

// The reserved words of SPEC.md §1.
export const RESERVED = new Set(`as true false break uses continue contract msg fn mod const
  static_assert if else match for in loop where while pub return yield self Self struct enum
  trait impl type let var mut ref own use extern unsafe ingot super`.split(/\s+/));
// `init`, `recv` and `assert`, which the grammar gives a fixed meaning (SPEC.md §1).
const CONTEXTUAL = new Set(["init", "recv", "assert"]);
// The type names of SPEC.md §1.
export const TYPES = /^(?:[ui](?:8|16|32|64|128|256)|usize|isize|bool|String|Address)$/;

// The integer literals of SPEC.md §1.
const NUMBER = /^(?:0[xX][0-9a-fA-F]+|0[oO][0-7]+|0[bB][01]+|[0-9]+(?:_[0-9]+)*)/;

export const fe0Tokens: StreamParser<null> = {
  name: "fe0",
  token(stream) {
    if (stream.eatSpace()) return null;
    if (stream.match(/^"(?:[^"\\]|\\.)*"?/)) return "string";
    if (stream.match("//")) {
      stream.skipToEnd();
      return "comment";
    }
    if (stream.match(/^#\[[^\]]*\]/)) return "meta";
    if (stream.match(NUMBER)) return "number";
    const word = stream.match(/^[A-Za-z_][A-Za-z0-9_]*/) as RegExpMatchArray | null;
    if (word) {
      const w = word[0];
      if (RESERVED.has(w) || CONTEXTUAL.has(w)) return "keyword";
      if (TYPES.test(w)) return "typeName";
      return /^[A-Z]/.test(w) ? "className" : "variableName";
    }
    stream.next();
    return null;
  },
};

export const fe0 = StreamLanguage.define(fe0Tokens);

// The colours of Fe0's tokens come from CSS custom properties in style.css, so that both
// themes fit.
export const fe0Highlight = HighlightStyle.define([
  { tag: tags.keyword, color: "var(--syn-keyword)" },
  { tag: tags.typeName, color: "var(--syn-type)" },
  { tag: tags.className, color: "var(--syn-name)" },
  { tag: tags.number, color: "var(--syn-number)" },
  { tag: tags.string, color: "var(--syn-string)" },
  { tag: tags.comment, color: "var(--syn-comment)", fontStyle: "italic" },
  { tag: tags.meta, color: "var(--syn-meta)" },
]);
