// One form for each `msg` variant that the outline guesses from the source
// (docs/adr/0032, "Call forms").
import { useId } from "react";
import type { Address } from "viem";
import { type Tx, callTx, transact } from "../chain/transact";
import { calldata, describeReturn } from "../domain/abi";
import type { Outline, Variant } from "../domain/outline";
import { useDeployment } from "../state/deployment";
import { formOf, useFieldTexts } from "../state/store";
import { isRunning, useAction } from "../state/transaction";
import { Fields } from "./Fields";
import { StatusLine } from "./Status";

function VariantForm({ variant, address }: { variant: Variant; address: Address }) {
  const deployed = useDeployment();
  const form = formOf(variant);
  const labelId = useId();
  const texts = useFieldTexts(form, variant.fields);
  const { status, run } = useAction();
  const running = isRunning(status);
  const tx = (): Tx => ({ to: address, data: calldata(variant.selector, texts) });

  const call = () => run("Calling…", async () =>
    describeReturn(variant.returns, await callTx(deployed, tx())));
  const send = () => run("Simulating…", async (progress) =>
    (await transact(deployed, tx(), progress)).mined);

  return (
    <section className="variant" aria-labelledby={labelId}>
      <h3><span id={labelId}>{variant.name}</span> <small>{variant.selector ?? "no selector"}
        {variant.returns && ` → ${variant.returns.type}`}</small></h3>
      <Fields form={form} texts={texts} />
      <div className="row">
        <button type="button" onClick={call} disabled={running}>Call</button>
        <button type="button" onClick={send} disabled={running}>Send</button>
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
    <div>
      {outline.variants.map((v) => (
        <VariantForm key={formOf(v)} variant={v} address={address} />
      ))}
    </div>
  );
}
