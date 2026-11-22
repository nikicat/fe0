// The playground's helpers that need no network and no library, so that Node can test them
// (playground/lib.test.mjs).

// The ABI type of each Fe0 type (SPEC.md §2).
const ABI_TYPES = { u256: "uint256", bool: "bool", Address: "address" };

// A variant of a `msg` type with its selector attribute.
const VARIANT = new RegExp(
  String.raw`#\[\s*selector\s*=\s*(?<lit>\w+)\s*\]` +
    String.raw`\s*(?<name>\w+)\s*(?<fields>\{[^}]*\})?\s*(?:->\s*(?<returns>\w+))?`,
  "g",
);

// Returns `source` with each `//` comment blanked out, so that offsets stay the same.
function blankComments(source) {
  return source.replace(/\/\/[^\r\n]*/g, (c) => " ".repeat(c.length));
}

// Returns the Fe0 type `type` with its ABI type, which is null when the Fe0 type has none.
function typed(type) {
  return { type, abi: ABI_TYPES[type] ?? null };
}

// Returns the parameters of a list such as `a: u256, to: Address`.
function params(list) {
  return list
    .split(",")
    .map((p) => p.trim())
    .filter((p) => p !== "")
    .map((p) => {
      const [name, type] = p.split(":").map((s) => s.trim());
      return { name, ...typed(type) };
    });
}

// Returns the 4-byte selector of the integer literal `lit`, such as `0xd09de08a`, `0b1` or
// `2`, as 0x-prefixed hex, or null when it is not one.
function selectorOf(lit) {
  let value;
  try {
    value = BigInt(lit.replaceAll("_", ""));
  } catch {
    return null;
  }
  if (value >= 1n << 32n) return null;
  return "0x" + value.toString(16).padStart(8, "0");
}

// Returns the block of braces that opens at `open` in `text`, without the braces.
function braced(text, open) {
  let depth = 0;
  for (let i = open; i < text.length; i++) {
    if (text[i] === "{") depth++;
    else if (text[i] === "}" && --depth === 0) return text.slice(open + 1, i);
  }
  return text.slice(open + 1);
}

// Returns the parameters of the program's `init` and each variant of its `msg` types, with its
// selector, fields and return type. It is a guess (playground/README.md, "Design").
export function outline(source) {
  const text = blankComments(source);
  const init = /\binit\s*\(([^)]*)\)/.exec(text);
  const variants = [];
  for (const m of text.matchAll(/\bmsg\s+(\w+)\s*\{/g)) {
    const body = braced(text, m.index + m[0].length - 1);
    for (const v of body.matchAll(VARIANT)) {
      const { lit, name, fields, returns } = v.groups;
      variants.push({
        msg: m[1],
        name,
        selector: selectorOf(lit),
        fields: fields ? params(fields.slice(1, -1)) : [],
        returns: returns ? typed(returns) : null,
      });
    }
  }
  return { init: init ? params(init[1]) : [], variants };
}

// Returns the line and column, both from 1, of the byte offset `offset` in `source`. Lines end
// at `\n`, `\r\n` or `\r`, as in tools/fegen.py's `LineCol.of`.
export function lineCol(source, offset) {
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

// Returns the number of lines of `source`, where lines end as in `lineCol`.
export const lineCount = (source) => lineCol(source, Infinity).line;

// Returns the UTF-16 index in `source` of the byte offset `offset`.
export function charIndex(source, offset) {
  const before = new TextEncoder().encode(source).slice(0, offset);
  return new TextDecoder().decode(before).length;
}

// The start of the fragment of a share link (playground/README.md). The rest is the program's
// UTF-8 bytes in base64url.
const FRAGMENT = "#src=";

// Returns the fragment of a share link that opens `source`.
export function linkFragment(source) {
  const bytes = new TextEncoder().encode(source);
  const base64 = btoa(String.fromCharCode(...bytes));
  return FRAGMENT + base64.replace(/\+/g, "-").replace(/\//g, "_");
}

// Returns the program that the fragment `hash` of a share link holds, or null when it holds
// none.
export function linkedSource(hash) {
  if (!hash.startsWith(FRAGMENT)) return null;
  const base64 = hash.slice(FRAGMENT.length).replace(/-/g, "+").replace(/_/g, "/");
  try {
    return new TextDecoder().decode(Uint8Array.from(atob(base64), (c) => c.charCodeAt(0)));
  } catch {
    return null;
  }
}

// Returns whether `text` is an address: `0x` and 40 hex digits.
export const isAddress = (text) => /^0x[0-9a-fA-F]{40}$/.test(text);

// The input of each ABI type in ABI_TYPES.
const INPUTS = {
  uint256: {
    placeholder: "0",
    parse(t) {
      if (/^(0x[0-9a-fA-F]+|[0-9]+)$/.test(t)) {
        const v = BigInt(t);
        if (v < 1n << 256n) return v;
      }
      throw new Error(`"${t}" is not a u256`);
    },
  },
  bool: {
    placeholder: "true or false",
    parse(t) {
      if (t === "true" || t === "false") return t === "true";
      throw new Error(`"${t}" is not true or false`);
    },
  },
  address: {
    placeholder: "0x…",
    parse(t) {
      if (isAddress(t)) return t;
      throw new Error(`"${t}" is not a 20-byte address`);
    },
  },
};

// Returns the value of the ABI type `abi` that `text` spells. Errors with Error when `text`
// spells no value of that type, or when `abi` has no input.
export function parseValue(abi, text) {
  const input = INPUTS[abi];
  if (!input) throw new Error(`the ABI type ${abi} has no input`);
  return input.parse(text.trim());
}

// Returns what an empty input of the ABI type `abi` shows, or "" when `abi` has no input.
export const placeholder = (abi) => INPUTS[abi]?.placeholder ?? "";

// The panic codes of SPEC.md §4, each with what it means.
export const PANICS = {
  0x01n: "assertion failed",
  0x11n: "arithmetic overflow or underflow",
  0x12n: "division or modulo by zero",
};
