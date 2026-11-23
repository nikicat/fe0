import { expect, test } from "vitest";
import { ABI_TYPES, type FeType, abiType, parseValue, placeholder } from "./values";

test("parseValue reads each ABI type", () => {
  expect(parseValue("uint256", " 0x10 ")).toBe(16n);
  expect(parseValue("bool", "false")).toBe(false);
  expect(() => parseValue("uint256", "-1")).toThrow();
  expect(() => parseValue("uint256", `0x1${"0".repeat(64)}`)).toThrow();
  expect(() => parseValue("address", "0x12")).toThrow();
  const account = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266";
  expect(parseValue("address", account)).toBe(account);
  expect(parseValue("address", account.toLowerCase())).toBe(account.toLowerCase());
  expect(() => parseValue("address", account.replace("F", "f"))).toThrow(/checksum/);
});

test("abiType maps each Fe0 type with an ABI type, and no other", () => {
  for (const [fe, abi] of Object.entries(ABI_TYPES)) {
    expect(abiType(fe as FeType)).toBe(abi);
    expect(placeholder(abi)).not.toBe("");
  }
  expect(abiType("Map" as FeType)).toBeNull();
  expect(abiType("toString" as FeType)).toBeNull();
});
