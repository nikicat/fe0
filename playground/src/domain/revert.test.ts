import { encodeErrorResult, parseAbi } from "viem";
import { expect, test } from "vitest";
import { COMPILE_ERROR, decodeRevert, describeRevert } from "./revert";

const messages = { "3014": { code: "N014", text: "cannot assign to this name" } };

test("a CompileError has the CLI's code and message, and its offset", () => {
  const args = [3014n, 101n] as const;
  const data = encodeErrorResult({ abi: [COMPILE_ERROR], errorName: "CompileError", args });
  const r = decodeRevert(data, messages);
  expect(r).toMatchObject({ kind: "compile", offset: 101 });
  expect(describeRevert(r)).toBe("N014 cannot assign to this name");
});

test("a panic names its meaning", () => {
  const panic = parseAbi(["error Panic(uint256)"]);
  const data = encodeErrorResult({ abi: panic, errorName: "Panic", args: [0x11n] });
  expect(describeRevert(decodeRevert(data, messages))).toBe(
    "Reverted with Panic(0x11): arithmetic overflow or underflow.");
});

test("other data is shown as it is", () => {
  expect(describeRevert(decodeRevert("0x", messages))).toBe("Reverted with no data.");
  expect(describeRevert(decodeRevert("0x1234", messages))).toBe("Reverted with 0x1234.");
});
