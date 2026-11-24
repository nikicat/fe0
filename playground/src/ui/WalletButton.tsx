import { useConnection } from "wagmi";
import { connectWallet } from "../chain/transact";
import { isRunning, useAction } from "../state/transaction";
import { HexText } from "./HexText";
import { StatusLine } from "./Status";

export function WalletButton() {
  const { address } = useConnection();
  const { status, run } = useAction();
  if (address) {
    return (
      <span className="wallet">
        <span className="dot" aria-hidden="true" /><HexText value={address} /></span>
    );
  }
  const connect = () => run("Connecting…", async () => {
    await connectWallet();
    return "Connected.";
  });
  return (
    <>
      <button type="button" className="primary" onClick={connect}
        disabled={isRunning(status)}>
        Connect wallet</button>
      {status.kind === "failed" && <StatusLine status={status} />}
    </>
  );
}
