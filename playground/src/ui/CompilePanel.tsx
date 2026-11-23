// The result of the latest compile on chain.
import { useId } from "react";
import { size } from "viem";
import type { DeployCode } from "../chain/compiler";
import type { CompileView } from "../state/queries";
import { CopyButton } from "./CopyButton";
import { FailureText, StatusText } from "./Status";

function CompiledLine({ code, gas }: { code: DeployCode; gas: bigint | null }) {
  return (
    <>
      <StatusText tone="ok">
        Compiled: {size(code).toLocaleString()} bytes of deploy code.
        {gas !== null
          && ` As a transaction the compile would cost ${gas.toLocaleString()} gas;`
          + " as an eth_call it is free."}
      </StatusText>
      <details>
        <summary>Deploy code</summary>
        <CopyButton label="Copy" text={() => code} />
        <pre>{code}</pre>
      </details>
    </>
  );
}

function CompileLine({ view }: { view: CompileView }) {
  switch (view.kind) {
    case "paused":
      return <StatusText tone="info">The compile waits for the network.</StatusText>;
    case "pending":
      return <StatusText tone="info">Compiling on chain…</StatusText>;
    case "failed":
      return <StatusText tone="err"><FailureText failure={view.failure} /></StatusText>;
    case "compiled":
      return <CompiledLine code={view.code} gas={view.gas} />;
  }
}

export function CompilePanel({ view }: { view: CompileView }) {
  const labelId = useId();
  return (
    <section className="panel" aria-labelledby={labelId}>
      <h2 id={labelId}>Compile</h2>
      <CompileLine view={view} />
    </section>
  );
}
