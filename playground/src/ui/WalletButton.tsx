import { useConnection } from "wagmi";
import { connectWallet } from "../chain/transact";
import { isRunning, useAction } from "../state/transaction";
import { shortHex } from "./Explorer";
import { StatusLine } from "./Status";

export function WalletButton() {
  const { address } = useConnection();
  const { status, run } = useAction();
  if (address) {
    return <button type="button" disabled>{shortHex(address)}</button>;
  }
  const connect = () => run("Connecting…", async () => {
    await connectWallet();
    return "Connected.";
  });
  return (
    <>
      <button type="button" onClick={connect} disabled={isRunning(status)}>
        Connect wallet</button>
      {status.kind === "failed" && <StatusLine status={status} />}
    </>
  );
}
