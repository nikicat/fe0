// One card for each `msg` variant that the outline guesses from the source
// (docs/adr/0032, "Call forms").
import { useId } from "react";
import type { Address } from "viem";
import { type Tx, callTx, transact } from "../chain/transact";
import type { Outline, Variant } from "../domain/outline";
import { useDeployment } from "../state/deployment";
import { Form, useFieldTexts } from "../state/store";
import { isRunning, useAction } from "../state/transaction";
import { Fields } from "./Fields";
import { StatusLine } from "./Status";

function VariantForm({ variant, address }: { variant: Variant; address: Address }) {
  const deployed = useDeployment();
  const form = Form.of(variant);
  const labelId = useId();
  const texts = useFieldTexts(form, variant.fields);
  const { status, run } = useAction();
  const running = isRunning(status);
  const tx = (): Tx => ({ to: address, data: variant.calldata(texts) });

  const call = () => run("Calling…", async () =>
    variant.describeReturn(await callTx(deployed, tx())));
  const send = () => run("Simulating…", async (progress) =>
    (await transact(deployed, tx(), progress)).mined);

  return (
    <section className="method" aria-labelledby={labelId}>
      <div className="method-head">
        <h3 id={labelId}>{variant.name}</h3>
        {variant.returns && <span className="type">→ {variant.returns.type}</span>}
        <code className="chip">{variant.selector ?? "no selector"}</code>
      </div>
      <Fields form={form} texts={texts} />
      <div className="inline">
        <button type="button" onClick={call} disabled={running}
          title="A free eth_call">Call</button>
        <button type="button" className="outline" onClick={send} disabled={running}
          title="A transaction from your wallet">Send</button>
      </div>
      <StatusLine status={status} />
    </section>
  );
}

export function CallForms({ outline, address }: { outline: Outline; address: Address }) {
  if (outline.variants.length === 0) {
    return <p className="hint">The program has no <code>msg</code> variants.</p>;
  }
  return (
    <div className="methods">
      {outline.variants.map((v) => (
        <VariantForm key={Form.of(v).id} variant={v} address={address} />
      ))}
    </div>
  );
}
