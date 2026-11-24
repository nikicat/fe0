// A status line: progress, a result or a failure.
import type { ReactNode } from "react";
import { type CompileFailure, type Failure, failureOf } from "../chain/failure";
import { describeRevert } from "../domain/revert";
import { store, useProgram } from "../state/store";
import type { Status } from "../state/transaction";
import { TxLink } from "./TxLink";

// The colours of a status line: progress, a result, or a failure.
type Tone = "info" | "ok" | "err";

// One line of status, announced to screen readers as it changes.
export function StatusText({ tone, children }: { tone: Tone; children: ReactNode }) {
  const className = tone === "info" ? "status" : `status ${tone}`;
  return <p className={className} role="status">{children}</p>;
}

// A compile error, with its place in the program it points into. The place is a link that
// selects it in the editor while the editor still holds that program.
function CompileErrorText({ failure }: { failure: CompileFailure }) {
  const { revert, program } = failure;
  const current = useProgram().source === program.source;
  const at = program.lineCol(revert.offset);
  const place = `${at.line}:${at.col}`;
  return (
    <>
      {current
        ? <a href="#" className="at" onClick={(e) => {
            e.preventDefault();
            store.select(revert.offset);
          }}>{place}</a>
        : place}{" "}
      {describeRevert(revert)}
    </>
  );
}

export function FailureText({ failure }: { failure: Failure }) {
  switch (failure.kind) {
    case "error":
      return <>{failure.text}</>;
    case "revert":
      return <>{describeRevert(failure.revert)}</>;
    case "compile":
      return <CompileErrorText failure={failure} />;
  }
}

// A thrown error, from a query or the wallet, as a status line.
export function ErrorLine({ error }: { error: unknown }) {
  return <StatusText tone="err"><FailureText failure={failureOf(error, null)} /></StatusText>;
}

export function StatusLine({ status }: { status: Status }) {
  switch (status.kind) {
    case "idle":
      return null;
    case "busy":
      return <StatusText tone="info">{status.text}</StatusText>;
    case "progress": {
      const p = status.progress;
      return p.step === "approve"
        ? <StatusText tone="info">Approve the transaction in your wallet…</StatusText>
        : <StatusText tone="info">
          Sent <TxLink hash={p.hash} />. Waiting for it to be mined…</StatusText>;
    }
    case "done":
      return <StatusText tone="ok">{status.text}</StatusText>;
    case "mined":
      return <StatusText tone="ok">Mined <TxLink hash={status.mined.hash} />,{" "}
        {status.mined.gasUsed.toLocaleString()} gas.</StatusText>;
    case "failed":
      return <StatusText tone="err"><FailureText failure={status.failure} /></StatusText>;
  }
}
