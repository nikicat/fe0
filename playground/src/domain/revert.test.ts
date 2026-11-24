import { encodeErrorResult, parseAbi } from "viem";
import { expect, test } from "vitest";
import type { Url } from "./config";
import { Repository } from "./repository";
import { COMPILE_ERROR, describeRevert } from "./revert";

const repository = new Repository("https://example.com/fe0" as Url, {
  "3014": { code: "N014", text: "cannot assign to this name" },
});

test("a CompileError has the CLI's code and message, and its offset", () => {
  const args = [3014n, 101n] as const;
  const data = encodeErrorResult({ abi: [COMPILE_ERROR], errorName: "CompileError", args });
  const r = repository.decodeRevert(data);
  expect(r).toMatchObject({ kind: "compile", offset: 101 });
  expect(describeRevert(r)).toBe("N014 cannot assign to this name");
});

test("a panic names its meaning", () => {
  const panic = parseAbi(["error Panic(uint256)"]);
  const data = encodeErrorResult({ abi: panic, errorName: "Panic", args: [0x11n] });
  expect(describeRevert(repository.decodeRevert(data))).toBe(
    "Reverted with Panic(0x11): arithmetic overflow or underflow.");
});

test("other data is shown as it is", () => {
  expect(describeRevert(repository.decodeRevert("0x"))).toBe("Reverted with no data.");
  expect(describeRevert(repository.decodeRevert("0x1234"))).toBe("Reverted with 0x1234.");
});
