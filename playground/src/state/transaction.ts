// The state of one form's call or transaction.
import { useCallback, useRef, useState } from "react";
import { type Failure, failureOf } from "../chain/failure";
import type { Mined, Progress } from "../chain/transact";
import type { Source } from "../domain/source";

export type Status =
  | { kind: "idle" }
  | { kind: "busy"; text: string }
  | { kind: "progress"; progress: Progress }
  | { kind: "done"; text: string }
  | { kind: "mined"; mined: Mined }
  | { kind: "failed"; failure: Failure };

// Checks whether an action has started and not yet ended or failed.
export function isRunning(status: Status): boolean {
  return status.kind === "busy" || status.kind === "progress";
}

// Returns the status of an action, and `run`, which runs one. The status follows the latest
// run only: a run started before it can no longer change it.
export function useAction() {
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const latest = useRef(0);
  const run = useCallback(
    async (
      busy: string,
      // Gets a callback for its progress, and returns what it ends on: a text, or the
      // transaction it mined, whose status keeps the link to it.
      action: (progress: (p: Progress) => void) => Promise<string | Mined>,
      // The program that the action sends to Compiler, which a compile error points into.
      source: Source | null = null,
    ) => {
      const id = ++latest.current;
      const show = (next: Status) => {
        if (id === latest.current) setStatus(next);
      };
      show({ kind: "busy", text: busy });
      try {
        const end = await action((progress) => show({ kind: "progress", progress }));
        show(typeof end === "string"
          ? { kind: "done", text: end }
          : { kind: "mined", mined: end });
      } catch (e) {
        show({ kind: "failed", failure: failureOf(e, source) });
      }
    },
    [],
  );
  return { status, run };
}
