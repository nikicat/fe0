// A status line: progress, a result or a failure.
import type { ReactNode } from "react";
import type { Hex } from "viem";
import type { CompileFailure, Failure } from "../chain/failure";
import { describeRevert } from "../domain/revert";
import { lineCol } from "../domain/source";
import { selectInEditor, useSource } from "../state/store";
import type { Status } from "../state/transaction";
import { Explorer, shortHex } from "./Explorer";

// The colours of a status line: progress, a result, or a failure.
type Tone = "info" | "ok" | "err";

// One line of status, announced to screen readers as it changes.
export function StatusText({ tone, children }: { tone: Tone; children: ReactNode }) {
  const className = tone === "info" ? "status" : `status ${tone}`;
  return <p className={className} role="status">{children}</p>;
}

// A compile error, with its place in the source it points into. The place is a link that
// selects it in the editor while the editor still holds that source.
function CompileErrorText({ failure }: { failure: CompileFailure }) {
  const { revert, source } = failure;
  const current = useSource() === source;
  const at = lineCol(source, revert.offset);
  const place = `${at.line}:${at.col}`;
  return (
    <>
      {current
        ? <a href="#" className="at" onClick={(e) => {
            e.preventDefault();
            selectInEditor(revert.offset);
          }}>{place}</a>
        : place}{" "}
      {describeRevert(revert)}
    </>
  );
}

function TxLink({ hash }: { hash: Hex }) {
  return <Explorer target={{ tx: hash }} text={shortHex(hash)} />;
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
