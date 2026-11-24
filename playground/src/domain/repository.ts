import { type Hex, decodeErrorResult } from "viem";
import type { ErrorCode, Message, Url } from "./config";
import { REVERT_ERRORS, type PanicCode, type Revert } from "./revert";
import type { ByteOffset } from "./source";

// The repository's documents that the page links to, in its docs/.
export type Doc = "SPEC.md" | "DEMO.md";

// This repository as config.ts records it (docs/adr/0032, "Configuration"): its documents and
// the native CLI's error messages.
export class Repository {
  // `url` is the repository's page. `messages` is keyed by the error code in decimal, as
  // tools/playground.py writes it.
  constructor(
    readonly url: Url,
    private readonly messages: Readonly<Record<string, Message>>,
  ) {}

  // Returns the URL of `doc` on the main branch.
  docUrl(doc: Doc): Url {
    return `${this.url}/blob/main/docs/${doc}` as Url;
  }

  // Returns the CLI's message for the error code `code`, or null when the CLI has none.
  message(code: ErrorCode): Message | null {
    return this.messages[code.toString()] ?? null;
  }

  // Returns what the revert data `data` means. Data that matches no known error is kept as
  // bytes.
  decodeRevert(data: Hex): Revert {
    if (data === "0x") return { kind: "empty" };
    let decoded;
    try {
      decoded = decodeErrorResult({ abi: REVERT_ERRORS, data });
    } catch {
      return { kind: "data", data };
    }
    switch (decoded.errorName) {
      case "CompileError": {
        const code = decoded.args[0] as ErrorCode;
        const offset = Number(decoded.args[1]) as ByteOffset;
        return { kind: "compile", code, message: this.message(code), offset };
      }
      case "UnlistedCompiler":
        return { kind: "unlisted", compiler: decoded.args[0] };
      case "FailedContractCreation":
        return { kind: "creation" };
      case "Panic":
        return { kind: "panic", code: decoded.args[0] as PanicCode };
      case "Error":
        return { kind: "error", reason: decoded.args[0] };
    }
  }
}
