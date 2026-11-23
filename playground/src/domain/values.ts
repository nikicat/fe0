import { type Address, isAddress } from "viem";

// The ABI type of each Fe0 type (SPEC.md §2) that has one.
export const ABI_TYPES = { u256: "uint256", bool: "bool", Address: "address" } as const;

export type AbiType = (typeof ABI_TYPES)[keyof typeof ABI_TYPES];

// The name of a Fe0 type, as a program spells it.
export type FeType = string & { readonly __brand: "FeType" };

// Returns the ABI type of the Fe0 type `type`, or null when it has none.
export const abiType = (type: FeType): AbiType | null =>
  Object.hasOwn(ABI_TYPES, type) ? ABI_TYPES[type as keyof typeof ABI_TYPES] : null;

export type Value = bigint | boolean | Address;

interface Input {
  placeholder: string;
  parse(text: string): Value;
}

const INPUTS: Record<AbiType, Input> = {
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
      throw new Error(`"${t}" is not an address, or its checksum is wrong`);
    },
  },
};

// Returns the value of the ABI type `abi` that `text` spells, ignoring spaces around it.
// Errors with Error when `text` spells no value of that type.
export const parseValue = (abi: AbiType, text: string): Value => INPUTS[abi].parse(text.trim());

// Returns what an empty input of the ABI type `abi` shows.
export const placeholder = (abi: AbiType): string => INPUTS[abi].placeholder;
