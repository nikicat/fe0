// The outline of a program, found in its source by regular expressions, since the page has no
// Fe0 parser. It is a guess (docs/adr/0032, "Call forms").
import { type Hex, concatHex, decodeAbiParameters } from "viem";
import { type EncodedArgs, type ParamText, argValues, encodeArgs } from "./abi";
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

// The 4 bytes that pick a variant, as calldata starts with them.
export type Selector = Hex & { readonly __brand: "Selector" };

export class Variant {
  constructor(
    // The `msg` type that holds the variant.
    readonly msg: string,
    readonly name: string,
    // The 4-byte selector, or null when the attribute's literal is not a 4-byte integer.
    readonly selector: Selector | null,
    readonly fields: Param[],
    readonly returns: Typed | null,
  ) {}

  // Returns the calldata that calls the variant with the fields `texts`. Errors as
  // `encodeArgs` does, or with Error when the variant has no selector.
  calldata(texts: readonly ParamText[]): Hex {
    if (this.selector === null) {
      throw new Error("The variant's selector is not a 4-byte integer.");
    }
    return concatHex([this.selector, encodeArgs(texts)]);
  }

  // Returns the text that shows the return data `result`. Errors when `result` is too short
  // for the return type.
  describeReturn(result: Hex): string {
    const { returns } = this;
    if (!returns) return "Returned.";
    if (!returns.abi) return `Returned ${result}`;
    const [value] = decodeAbiParameters([{ type: returns.abi }], result);
    return `Returned ${String(value)}`;
  }
}

export class Outline {
  // The contract's name, or null when the source names none.
  readonly name: string | null;
  readonly init: Param[];
  readonly variants: Variant[];

  constructor(name: string | null, init: Param[], variants: Variant[]) {
    this.name = name;
    this.init = init;
    this.variants = variants;
  }

  // Returns the outline of `source`.
  static of(source: Source): Outline {
    const text = blankComments(source);
    const init = INIT.exec(text);
    const variants: Variant[] = [];
    for (const m of text.matchAll(MSG)) {
      const body = braced(text, m.index + m[0].length - 1);
      for (const v of body.matchAll(VARIANT)) {
        const { lit = "", name = "", fields, returns } = v.groups ?? {};
        variants.push(new Variant(m.groups?.name ?? "", name, selectorOf(lit),
          params(fields ?? ""), returns ? typed(returns) : null));
      }
    }
    const name = CONTRACT.exec(text)?.groups?.name ?? null;
    return new Outline(name, params(init?.groups?.params ?? ""), variants);
  }

  // Returns the call that creates the contract with the ABI encoding `args`, such as
  // `Counter(2)`. It has `…` for the arguments when `args` does not decode as `init`'s
  // parameters. Returns null when the source names no contract.
  constructorCall(args: EncodedArgs): string | null {
    if (this.name === null) return null;
    return `${this.name}(${this.#initValues(args)?.join(", ") ?? "…"})`;
  }

  // Returns the text of `init`'s arguments in the ABI encoding `args`, such as `from = 2`. It
  // is "none" when `init` takes none. It is `args` itself when `args` does not decode as
  // `init`'s parameters.
  argsText(args: EncodedArgs): string {
    const values = this.#initValues(args);
    if (values === null) return args;
    if (values.length === 0) return "none";
    return values.map((v, i) => `${this.init[i]!.name} = ${v}`).join(", ");
  }

  // Returns the text of each of `init`'s arguments in `args`, or null when `args` does not
  // decode as `init`'s parameters.
  #initValues(args: EncodedArgs): string[] | null {
    return argValues(this.init, args);
  }
}

// The head of the contract, with its name.
const CONTRACT = /\bcontract\s+(?<name>\w+)/;

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
