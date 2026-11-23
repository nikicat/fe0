import { BaseError } from "viem";
import { config } from "../config";
import { type Revert, decodeRevert } from "../domain/revert";
import type { Source } from "../domain/source";
import { revertData } from "./revertData";

// Compiler's `CompileError`, with the source it points into, which the editor may since have
// changed.
export interface CompileFailure {
  kind: "compile";
  revert: Extract<Revert, { kind: "compile" }>;
  source: Source;
}

export type Failure =
  | CompileFailure
  | { kind: "revert"; revert: Revert }
  | { kind: "error"; text: string };

// Returns the failure that the page shows for any thrown value. `source` is the program that
// the failed call sent to Compiler, or null when it sent none. A `CompileError` is a compile
// failure only when `source` is not null.
export function failureOf(error: unknown, source: Source | null): Failure {
  const data = revertData(error);
  if (data !== null) {
    const revert = decodeRevert(data, config.messages);
    return revert.kind === "compile" && source !== null
      ? { kind: "compile", revert, source }
      : { kind: "revert", revert };
  }
  const text =
    error instanceof BaseError
      ? error.shortMessage
      : error instanceof Error
        ? error.message
        : String(error);
  return { kind: "error", text };
}
