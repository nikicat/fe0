import { type Hex, concatHex, decodeAbiParameters, encodeAbiParameters } from "viem";
import type { Param, Selector, Typed } from "./outline";
import { parseValue } from "./values";

// A parameter with the text of its field.
export interface ParamText {
  param: Param;
  text: string;
}

// Returns the ABI encoding of the values that `texts` spell. Errors when a parameter's type has
// no ABI type, or when its text spells no value of that type. The message starts with the
// parameter's name.
export function encodeArgs(texts: readonly ParamText[]): Hex {
  const args = texts.map(({ param: p, text }) => {
    if (!p.abi) throw new Error(`${p.name} has the type ${p.type}, which has no ABI type`);
    try {
      return { type: p.abi, value: parseValue(p.abi, text) };
    } catch (e) {
      throw new Error(`${p.name}: ${(e as Error).message}`);
    }
  });
  return encodeAbiParameters(
    args.map(({ type }) => ({ type })),
    args.map(({ value }) => value),
  );
}

// Returns the calldata of a variant with the selector `selector` and the fields `texts`. Errors
// as `encodeArgs` does, or with Error when `selector` is null.
export function calldata(selector: Selector | null, texts: readonly ParamText[]): Hex {
  if (selector === null) {
    throw new Error("The variant's selector is not a 4-byte integer.");
  }
  return concatHex([selector, encodeArgs(texts)]);
}

// Returns the text that shows the return data `result` of a variant whose return type is
// `returns`. Errors when `result` is too short for that type.
export function describeReturn(returns: Typed | null, result: Hex): string {
  if (!returns) return "Returned.";
  if (!returns.abi) return `Returned ${result}`;
  const [value] = decodeAbiParameters([{ type: returns.abi }], result);
  return `Returned ${String(value)}`;
}
