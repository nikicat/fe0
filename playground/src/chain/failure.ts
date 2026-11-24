import { BaseError } from "viem";
import type { Revert } from "../domain/revert";
import type { Program } from "../domain/source";
import { repository } from "./repository";
import { revertData } from "./revertData";

// Compiler's `CompileError`, with the program it points into, which the editor may since
// have changed.
export interface CompileFailure {
  kind: "compile";
  revert: Extract<Revert, { kind: "compile" }>;
  program: Program;
}

export type Failure =
  | CompileFailure
  | { kind: "revert"; revert: Revert }
  | { kind: "error"; text: string };

// Returns the failure that the page shows for any thrown value. `program` is the program that
// the failed call sent to Compiler, or null when it sent none. A `CompileError` is a compile
// failure only when `program` is not null.
export function failureOf(error: unknown, program: Program | null): Failure {
  const data = revertData(error);
  if (data !== null) {
    const revert = repository.decodeRevert(data);
    return revert.kind === "compile" && program !== null
      ? { kind: "compile", revert, program }
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
