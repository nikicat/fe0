import { type Address, type Hex, parseAbi, parseAbiItem } from "viem";
import type { ErrorCode, Message } from "./config";
import type { ByteOffset } from "./source";

// Compiler's one error. domain/ does not import src/config.ts (docs/adr/0032), so the error
// is declared here, and chain/failure.test.ts checks it against Compiler's interface.
export const COMPILE_ERROR = parseAbiItem("error CompileError(uint256 code, uint256 offset)");

// Registry's error for a compiler that CompilerRegistry does not list, declared here for the
// same reason, and checked against Registry's interface.
export const UNLISTED_COMPILER = parseAbiItem("error UnlistedCompiler(address compiler)");

// CreateX's error when it creates no contract, which Registry passes on
// (docs/adr/0031-deployment-registry.md, "Deploying").
const FAILED_CREATION = parseAbiItem("error FailedContractCreation(address emitter)");

// The errors that a revert is decoded with.
export const REVERT_ERRORS = [
  COMPILE_ERROR,
  UNLISTED_COMPILER,
  FAILED_CREATION,
  ...parseAbi(["error Panic(uint256 code)", "error Error(string reason)"]),
] as const;

// The code of a Solidity `Panic`, such as those of SPEC.md §4.
export type PanicCode = bigint & { readonly __brand: "PanicCode" };

// The panic codes of SPEC.md §4, each with what it means.
const PANICS: ReadonlyMap<bigint, string> = new Map([
  [0x01n, "assertion failed"],
  [0x11n, "arithmetic overflow or underflow"],
  [0x12n, "division or modulo by zero"],
]);

export type Revert =
  // Compiler's `CompileError(code, offset)`, with the CLI's message when the code has one.
  | { kind: "compile"; code: ErrorCode; message: Message | null; offset: ByteOffset }
  | { kind: "unlisted"; compiler: Address }
  | { kind: "creation" }
  | { kind: "panic"; code: PanicCode }
  | { kind: "error"; reason: string }
  | { kind: "empty" }
  | { kind: "data"; data: Hex };

// Returns the text of `revert`. A compile error's text has no line or column.
export function describeRevert(revert: Revert): string {
  switch (revert.kind) {
    case "compile":
      return revert.message
        ? `${revert.message.code} ${revert.message.text}`
        : `error ${revert.code}`;
    case "unlisted":
      return `The registry does not accept the compiler ${revert.compiler}.`;
    case "creation":
      return "CreateX created no contract.";
    case "panic": {
      const digits = revert.code.toString(16).padStart(2, "0");
      const meaning = PANICS.get(revert.code) ?? "unknown code";
      return `Reverted with Panic(0x${digits}): ${meaning}.`;
    }
    case "error":
      return `Reverted with Error(${JSON.stringify(revert.reason)}).`;
    case "empty":
      return "Reverted with no data.";
    case "data":
      return `Reverted with ${revert.data}.`;
  }
}
