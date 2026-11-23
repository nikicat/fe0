import { type Hex, decodeErrorResult, parseAbi, parseAbiItem } from "viem";
import { type Config, type ErrorCode, type Message, cliMessage } from "./config";
import type { ByteOffset } from "./source";

// Compiler's one error. domain/ does not import src/config.ts (docs/adr/0032), so the error
// is declared here, and chain/failure.test.ts checks it against Compiler's interface.
export const COMPILE_ERROR = parseAbiItem("error CompileError(uint256 code, uint256 offset)");

// The errors that a revert is decoded with: Compiler's and Solidity's two.
const ERRORS = [
  COMPILE_ERROR,
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
  | { kind: "panic"; code: PanicCode }
  | { kind: "error"; reason: string }
  | { kind: "empty" }
  | { kind: "data"; data: Hex };

// Returns what the revert data `data` means. A `CompileError`'s code is looked up in
// `messages`. Data that matches no known error is kept as bytes.
export function decodeRevert(data: Hex, messages: Config["messages"]): Revert {
  if (data === "0x") return { kind: "empty" };
  let decoded;
  try {
    decoded = decodeErrorResult({ abi: ERRORS, data });
  } catch {
    return { kind: "data", data };
  }
  switch (decoded.errorName) {
    case "CompileError": {
      const code = decoded.args[0] as ErrorCode;
      const message = cliMessage(messages, code);
      const offset = Number(decoded.args[1]) as ByteOffset;
      return { kind: "compile", code, message, offset };
    }
    case "Panic":
      return { kind: "panic", code: decoded.args[0] as PanicCode };
    case "Error":
      return { kind: "error", reason: decoded.args[0] };
  }
}

// Returns the text of `revert`. A compile error's text has no line or column.
export function describeRevert(revert: Revert): string {
  switch (revert.kind) {
    case "compile":
      return revert.message
        ? `${revert.message.code} ${revert.message.text}`
        : `error ${revert.code}`;
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
