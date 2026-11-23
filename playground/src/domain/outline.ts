// The outline of a program: its `init` and its `msg` variants, read from the source. It is a
// guess (docs/adr/0032, "Call forms").
import type { Hex } from "viem";
import type { Source } from "./source";
import { type AbiType, type FeType, abiType } from "./values";

// A Fe0 type, with its ABI type, which is null when it has none.
export interface Typed {
  type: FeType;
  abi: AbiType | null;
}

export interface Param extends Typed {
  name: string;
}

export interface Variant {
  // The `msg` type that holds the variant.
  msg: string;
  name: string;
  // The 4-byte selector, or null when the attribute's literal is not a 4-byte integer.
  selector: Selector | null;
  fields: Param[];
  returns: Typed | null;
}

// The 4 bytes that pick a variant, as calldata starts with them.
export type Selector = Hex & { readonly __brand: "Selector" };

export interface Outline {
  init: Param[];
  variants: Variant[];
}

// The contract's `init` and its parameter list.
const INIT = /\binit\s*\((?<params>[^)]*)\)/;

// The head of a `msg` type, up to the brace that opens its body.
const MSG = /\bmsg\s+(?<name>\w+)\s*\{/g;

// A variant of a `msg` type with its selector attribute.
const VARIANT = new RegExp(
  String.raw`#\[\s*selector\s*=\s*(?<lit>\w+)\s*\]` +
    String.raw`\s*(?<name>\w+)\s*(?:\{(?<fields>[^}]*)\})?\s*(?:->\s*(?<returns>\w+))?`,
  "g",
);

// Returns `source` with each `//` comment blanked out, so that offsets stay the same.
const blankComments = (source: Source): string =>
  source.replace(/\/\/[^\r\n]*/g, (c) => " ".repeat(c.length));

function typed(text: string): Typed {
  const type = text as FeType;
  return { type, abi: abiType(type) };
}

// Returns the parameters of a list such as `a: u256, to: Address`.
function params(list: string): Param[] {
  return list
    .split(",")
    .map((p) => p.trim())
    .filter((p) => p !== "")
    .map((p) => {
      const [name = "", type = ""] = p.split(":").map((s) => s.trim());
      return { name, ...typed(type) };
    });
}

// Returns the selector that the integer literal `lit` spells, such as `0xd09de08a`, `0b1` or
// `2`, with or without underscores.
function selectorOf(lit: string): Selector | null {
  let value: bigint;
  try {
    value = BigInt(lit.replaceAll("_", ""));
  } catch {
    return null;
  }
  if (value >= 1n << 32n) return null;
  return `0x${value.toString(16).padStart(8, "0")}` as Selector;
}

// Returns the block of braces that opens at `open` in `text`, without the braces.
function braced(text: string, open: number): string {
  let depth = 0;
  for (let i = open; i < text.length; i++) {
    if (text[i] === "{") depth++;
    else if (text[i] === "}" && --depth === 0) return text.slice(open + 1, i);
  }
  return text.slice(open + 1);
}

export function outline(source: Source): Outline {
  const text = blankComments(source);
  const init = INIT.exec(text);
  const variants: Variant[] = [];
  for (const m of text.matchAll(MSG)) {
    const body = braced(text, m.index + m[0].length - 1);
    for (const v of body.matchAll(VARIANT)) {
      const { lit = "", name = "", fields, returns } = v.groups ?? {};
      variants.push({
        msg: m.groups?.name ?? "",
        name,
        selector: selectorOf(lit),
        fields: params(fields ?? ""),
        returns: returns ? typed(returns) : null,
      });
    }
  }
  return { init: params(init?.groups?.params ?? ""), variants };
}
