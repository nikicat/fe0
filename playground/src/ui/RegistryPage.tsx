// The registry's list of contracts, newest first (docs/adr/0032, "Routes").
import { useState } from "react";
import { type Address, isAddressEqual } from "viem";
import { useConnection } from "wagmi";
import { connectWallet } from "../chain/transact";
import { ListCursor } from "../domain/registryList";
import { EDITOR_HASH, Route } from "../domain/route";
import { Program } from "../domain/source";
import { useDeployment } from "../state/deployment";
import { useRecords, useRegistryPage } from "../state/queries";
import { router, useContractLink } from "../state/route";
import { isRunning, useAction } from "../state/transaction";
import { CompilerName } from "./CompilerName";
import { HexText } from "./HexText";
import { SaltText } from "./SaltText";
import { SourcifyLink } from "./SourcifyLink";
import { ErrorLine, StatusLine } from "./Status";

function Rows({ items }: { items: readonly Address[] }) {
  const records = useRecords(items);
  const contract = useContractLink();
  return (
    <>
      {records.isError && <ErrorLine error={records.error} />}
      <table className="table">
        <thead>
          <tr><th>Contract</th><th>Address</th><th className="hide-phone">Salt</th>
            <th className="hide-phone">Compiler</th></tr>
        </thead>
        <tbody>
          {items.map((address) => {
            const record = records.data?.get(address) ?? null;
            const name = record
              && new Program(record.source).outline().constructorCall(record.args);
            const href = contract.href(address);
            return (
              <tr key={address}>
                <td><a className="row-link" href={href}>
                  {records.isPending ? "…" : name ?? "Unnamed"}</a></td>
                <td className="mono"><a href={href}><HexText value={address} /></a></td>
                <td className="mono hide-phone">
                  {record === null ? "" : <SaltText salt={record.salt} />}</td>
                <td className="hide-phone">
                  {record === null ? "" : <CompilerName address={record.compiler} />}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

// The registry list that `account` names, as in ListCursor, a page at a time.
function List({ account }: { account: Address | null }) {
  const [cursor, setCursor] = useState(() => new ListCursor(account));
  const read = useRegistryPage(cursor);
  if (read.isPending) return <p className="hint">Reading the registry…</p>;
  if (read.isError) {
    return <ErrorLine error={read.error} />;
  }
  const page = read.data;
  const { total, items } = page;
  if (total === 0n) {
    return <p className="empty">No contracts yet.{" "}
      <a href={EDITOR_HASH}>Deploy one</a></p>;
  }
  const { newest, oldest } = page.shown();
  const newer = page.newer();
  const older = page.older();
  return (
    <>
      <Rows items={items} />
      <div className="pager">
        <span className="hint">{newest.toLocaleString()}–{oldest.toLocaleString()} of{" "}
          {total.toLocaleString()}</span>
        <div className="inline">
          <button type="button" disabled={newer === null}
            onClick={() => newer && setCursor(newer)}>Newer</button>
          <button type="button" disabled={older === null}
            onClick={() => older && setCursor(older)}>Older</button>
        </div>
      </div>
    </>
  );
}

// Switches between every contract and the wallet's own, connecting the wallet first.
function Filter({ account }: { account: Address | null }) {
  const { address } = useConnection();
  const { status, run } = useAction();
  const mine = address !== undefined && account !== null && isAddressEqual(address, account);
  const showMine = () => run("Connecting…", async () => {
    router.navigate(Route.registry(await connectWallet()));
    return "Connected.";
  });
  return (
    <>
      <div className="segmented" role="group" aria-label="Contracts">
        <button type="button" aria-pressed={account === null}
          onClick={() => router.navigate(Route.registry())}>All</button>
        <button type="button" aria-pressed={mine} onClick={showMine}
          disabled={isRunning(status)}>Mine</button>
      </div>
      {status.kind === "failed" && <StatusLine status={status} />}
    </>
  );
}

export function RegistryPage({ account }: { account: Address | null }) {
  const { chain, registry } = useDeployment();
  return (
    <div className="page" aria-label="Registry">
      <div className="page-head">
        <h1>Registry</h1>
        <p className="lede">Every Fe0 program deployed through the registry on {chain.name},
          newest first, with the source it was compiled from.</p>
        <div className="meta-row">
          <span className="hint">Registry</span>
          <SourcifyLink verified={registry} />
        </div>
      </div>
      <section className="card flush">
        <div className="card-head">
          {account === null
            ? <h2>All contracts</h2>
            : <h2>Deployed by <HexText value={account} /></h2>}
          <Filter account={account} />
        </div>
        <List key={account ?? ""} account={account} />
      </section>
    </div>
  );
}
