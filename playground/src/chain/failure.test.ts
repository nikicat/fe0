import { encodeErrorResult } from "viem";
import { expect, test } from "vitest";
import { compilerAbi, config } from "../config";
import { COMPILE_ERROR, decodeRevert } from "../domain/revert";
import { failureOf } from "./failure";

test("the CompileError that domain/ decodes is the one in Compiler's interface", () => {
  expect(compilerAbi).toContainEqual(COMPILE_ERROR);
});

test("a CompileError's code finds its message in config.ts", () => {
  const [key, message] = Object.entries(config.messages)[0]!;
  const args = [BigInt(key), 0n] as const;
  const data = encodeErrorResult({ abi: [COMPILE_ERROR], errorName: "CompileError", args });
  expect(decodeRevert(data, config.messages)).toMatchObject({ kind: "compile", message });
});

test("any thrown value gives a failure", () => {
  expect(failureOf(null, null)).toEqual({ kind: "error", text: "null" });
  expect(failureOf(new Error("boom"), null)).toEqual({ kind: "error", text: "boom" });
});
