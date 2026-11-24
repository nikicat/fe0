import { type Hex, decodeAbiParameters, encodeAbiParameters } from "viem";
import type { Param } from "./outline";
import { parseValue } from "./values";

// The ABI encoding of the arguments of a program's `init`.
export type EncodedArgs = Hex & { readonly __brand: "EncodedArgs" };

// A parameter with the text of its field.
export interface ParamText {
  param: Param;
  text: string;
}

// Returns the ABI encoding of the values that `texts` spell. Errors when a parameter's type has
// no ABI type, or when its text spells no value of that type. The message starts with the
// parameter's name.
export function encodeArgs(texts: readonly ParamText[]): EncodedArgs {
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
  ) as EncodedArgs;
}

// The ABI encoding of a form's arguments, or the message of the error that encoding them gave.
export type ArgsResult = { args: EncodedArgs } | { error: string };

// Returns what `encodeArgs(texts)` returns, or the message of its error.
export function tryEncodeArgs(texts: readonly ParamText[]): ArgsResult {
  try {
    return { args: encodeArgs(texts) };
  } catch (e) {
    return { error: (e as Error).message };
  }
}

// Returns the text of each value of `params` that the ABI encoding `args` holds. Returns null
// when a parameter's type has no ABI type, or when `args` does not hold one value of each type
// and nothing more.
export function argValues(params: readonly Param[], args: EncodedArgs): string[] | null {
  const types = params.map((p) => p.abi);
  if (types.some((t) => t === null)) return null;
  const abi = types.map((type) => ({ type: type! }));
  let values: readonly unknown[];
  try {
    values = decodeAbiParameters(abi, args);
  } catch {
    return null;
  }
  if (encodeAbiParameters(abi, values) !== args) return null;
  return values.map(String);
}
