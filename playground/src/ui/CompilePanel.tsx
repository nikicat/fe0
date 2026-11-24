// The result of the latest compile on chain.
import { size } from "viem";
import type { DeployCode } from "../domain/createx";
import { useDeployment } from "../state/deployment";
import type { CompileView } from "../state/queries";
import { CopyButton } from "./CopyButton";
import { SourcifyLink } from "./SourcifyLink";
import { FailureText, StatusText } from "./Status";

function CompiledLine({ code, gas }: { code: DeployCode; gas: bigint | null }) {
  return (
    <>
      <StatusText tone="ok">
        Compiled: {size(code).toLocaleString()} bytes of deploy code.
        {gas !== null && <span className="muted"> {gas.toLocaleString()} gas as a
          transaction, free as an eth_call.</span>}
      </StatusText>
      <details className="deploy-code">
        <summary>Deploy code</summary>
        <div className="deploy-code-body">
          <CopyButton label="Copy" text={() => code} />
          <pre>{code}</pre>
        </div>
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
  const { compiler } = useDeployment();
  return (
    <section className={`compile-bar ${view.kind}`} aria-label="Compile">
      <span className="indicator" aria-hidden="true" />
      <div className="compile-text"><CompileLine view={view} /></div>
      <span className="compile-by hide-tablet">by Compiler{" "}
        <SourcifyLink verified={compiler} /></span>
    </section>
  );
}
