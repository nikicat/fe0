import { encodeErrorResult } from "viem";
import { expect, test } from "vitest";
import { compilerAbi, config, registryAbi } from "../config";
import { COMPILE_ERROR, UNLISTED_COMPILER } from "../domain/revert";
import { failureOf } from "./failure";
import { repository } from "./repository";

test("the CompileError that domain/ decodes is the one in Compiler's interface", () => {
  expect(compilerAbi).toContainEqual(COMPILE_ERROR);
});

test("the UnlistedCompiler that domain/ decodes is the one in Registry's interface", () => {
  expect(registryAbi).toContainEqual(UNLISTED_COMPILER);
});

test("a CompileError's code finds its message in config.ts", () => {
  const [key, message] = Object.entries(config.messages)[0]!;
  const args = [BigInt(key), 0n] as const;
  const data = encodeErrorResult({ abi: [COMPILE_ERROR], errorName: "CompileError", args });
  expect(repository.decodeRevert(data)).toMatchObject({ kind: "compile", message });
});

test("any thrown value gives a failure", () => {
  expect(failureOf(null, null)).toEqual({ kind: "error", text: "null" });
  expect(failureOf(new Error("boom"), null)).toEqual({ kind: "error", text: "boom" });
});
