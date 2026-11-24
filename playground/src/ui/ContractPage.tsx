// A contract's page. Its call forms come from the program in the editor, which the page fills
// with the contract's source when the registry recorded it (docs/adr/0032, "Contract pages").
import { useEffect, useMemo } from "react";
import type { Address } from "viem";
import type { Recorded } from "../chain/registry";
import type { ChainId } from "../domain/config";
import type { Outline } from "../domain/outline";
import { EDITOR_HASH, Route } from "../domain/route";
import { Program, type Source } from "../domain/source";
import { useDeployment } from "../state/deployment";
import { router } from "../state/route";
import { type RecordView, useContract, useRecord } from "../state/queries";
import { store, useOutline, useProgram } from "../state/store";
import { CallForms } from "./CallForms";
import { CodeView } from "./CodeView";
import { CompilerName } from "./CompilerName";
import { CopyButton } from "./CopyButton";
import { SaltText } from "./SaltText";
import { ErrorLine } from "./Status";

function ContractBadges({ address }: { address: Address }) {
  const contract = useContract(address).query;
  if (contract.isPending) return <span className="badge">Reading…</span>;
  if (contract.isError) {
    return <ErrorLine error={contract.error} />;
  }
  if (contract.data.kind === "empty") {
    return <span className="badge err">No contract at this address</span>;
  }
  const { size, version } = contract.data;
  return (
    <>
      <span className="badge">{size.toLocaleString()} bytes of code</span>
      {version !== null && <span className="badge">version {version}</span>}
    </>
  );
}

// Whether the registry recorded the contract, as a badge. A failed read shows none, since the
// page shows its error.
function RegistryBadge({ view }: { view: RecordView }) {
  switch (view.kind) {
    case "reading": return <span className="badge">Reading the registry…</span>;
    case "failed": return null;
    case "recorded": return <span className="badge ok">In the registry</span>;
    case "unrecorded": return <span className="badge warn">Not in the registry</span>;
  }
}

// Opens the editor with `source`.
function editSource(source: Source): void {
  store.setSource(source);
  router.navigate(Route.editor());
}

function RecordCard({ record, outline }: { record: Recorded; outline: Outline }) {
  return (
    <section className="card" aria-label="Record">
      <h2>Record</h2>
      <dl className="facts">
        <dt>Compiler</dt>
        <dd><CompilerName address={record.compiler} /></dd>
        <dt>Constructor arguments</dt>
        <dd className="mono">{outline.argsText(record.args)}</dd>
        <dt>Block</dt>
        <dd className="mono">{record.block.toLocaleString()}</dd>
        <dt>Salt</dt>
        <dd className="mono"><SaltText salt={record.salt} /></dd>
      </dl>
    </section>
  );
}

function SourceCard({ record }: { record: Recorded }) {
  const editor = useProgram().source;
  return (
    <section className="card" aria-label="Source">
      <div className="card-head">
        <h2>Source</h2>
        <button type="button" onClick={() => editSource(record.source)}>Open in editor</button>
      </div>
      {editor !== record.source && <p className="callout">The editor holds another program,
        and the methods come from it. <button type="button" className="link"
          onClick={() => store.setSource(record.source)}>Use this source</button></p>}
      <CodeView source={record.source} label="Contract source" />
    </section>
  );
}

export function ContractPage({ address, routeSource }:
  { address: Address; routeSource: Source | null }) {
  const deployed = useDeployment();
  const outline = useOutline();
  const view = useRecord(address);
  // The effect depends on the source text, not the record object, so that reading the same
  // record again does not undo the user's edits.
  const recordedSource = view.kind === "recorded" ? view.record.source : null;
  useEffect(() => {
    if (routeSource === null && recordedSource !== null) store.setSource(recordedSource);
  }, [routeSource, recordedSource]);
  const recorded = useMemo(
    () => recordedSource === null ? null : new Program(recordedSource).outline(),
    [recordedSource]);

  return (
    <div className="page">
      <div className="page-head">
        <p className="crumbs"><a href={Route.registry().hash()}>Registry</a> / contract</p>
        <h1>{recorded?.name ?? "Contract"}</h1>
        <div className="meta-row">
          <code className="addr">{address}</code>
          <CopyButton label="Copy" text={() => address} />
        </div>
        <div className="badges">
          <span className="badge">{deployed.chain.name}</span>
          <ContractBadges address={address} />
          <RegistryBadge view={view} />
        </div>
      </div>
      {view.kind === "failed" && <ErrorLine error={view.error} />}
      <div className="contract-grid">
        <section className="card" aria-label="Methods">
          <div className="card-head">
            <h2>Methods</h2>
            <span className="hint">Call is a free <code>eth_call</code>. Send is a transaction
              from your wallet.</span>
          </div>
          {view.kind === "unrecorded" && <p className="callout">The registry has no
            record of this contract, so the methods come from the program in the editor, which
            may not be the contract's. <a href={EDITOR_HASH}>Edit it</a></p>}
          <CallForms outline={outline} address={address} />
        </section>
        {view.kind === "recorded" && recorded !== null && <aside className="stack">
          <RecordCard record={view.record} outline={recorded} />
          <SourceCard record={view.record} />
        </aside>}
      </div>
    </div>
  );
}

// The page of a contract on a chain that config.ts lacks, which the page can neither read
// nor call.
export function UnknownChainPage({ chainId, address }: { chainId: ChainId; address: Address }) {
  return (
    <div className="page">
      <div className="page-head">
        <h1>Contract</h1>
        <div className="meta-row"><code className="addr">{address}</code></div>
      </div>
      <p className="callout err">The page knows no chain {chainId}.{" "}
        <a href={EDITOR_HASH}>Open the editor</a></p>
    </div>
  );
}
