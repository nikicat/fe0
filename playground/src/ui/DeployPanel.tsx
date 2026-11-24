import { Registry } from "../chain/registry";
import type { Creation, DeployCode } from "../domain/createx";
import { Route } from "../domain/route";
import type { Program } from "../domain/source";
import { useDeployPreview } from "../state/deployPreview";
import { useDeployment } from "../state/deployment";
import { useRememberRecord } from "../state/queries";
import { useContractLink } from "../state/route";
import { Form, store } from "../state/store";
import { isRunning, useAction } from "../state/transaction";
import { Fields } from "./Fields";
import { HexText } from "./HexText";
import { StatusLine, StatusText } from "./Status";

// The deploy form shows the address before deploying, and opens the contract when it already
// exists (docs/adr/0031-deployment-registry.md, "Deploying").
export function DeployPanel({ program, code }:
  { program: Program; code: DeployCode | null }) {
  const registry = Registry.of(useDeployment());
  const { status, run } = useAction();
  const remember = useRememberRecord();
  const contract = useContractLink();
  const { texts, saltText, encoded, creation, address, existing, call } =
    useDeployPreview(program, code);

  const deploy = (creation: Creation) =>
    run("Simulating the deployment…", async (progress) => {
      const reached = await registry.deploy(creation, progress);
      if (reached.record !== null) remember(reached.address, reached.record);
      contract.open(reached.address);
      return `Deployed at ${reached.address}.`;
    }, program);

  return (
    <section className="card" aria-label="Deploy">
      <h2>Deploy{call !== null && <span className="muted"> {call}</span>}</h2>
      <p className="hint">The <a href={Route.registry().hash()}>registry</a> compiles the
        program, creates the contract and records it with its source. The same program,
        arguments and salt always give the same address, for everyone.</p>
      {texts.length > 0 && <h3 className="label">Constructor arguments</h3>}
      <Fields form={Form.init} texts={texts} />
      {"error" in encoded && <StatusText tone="err">{encoded.error}</StatusText>}
      <label className="field">
        <span>salt (optional)</span>
        <input value={saltText} onChange={(e) => store.setSaltText(e.target.value)}
          spellCheck={false} placeholder="any text, for a separate instance" />
      </label>
      {address !== null && <p className="hint">
        {existing !== null ? "Already deployed at" : "Deploys to"} <HexText value={address} />
      </p>}
      {existing !== null
        ? <button type="button" className="primary wide"
            onClick={() => contract.open(existing)}>
            Open</button>
        : <button type="button" className="primary wide"
            onClick={creation !== null ? () => deploy(creation) : undefined}
            disabled={"error" in encoded || isRunning(status)}>Deploy</button>}
      <StatusLine status={status} />
    </section>
  );
}
