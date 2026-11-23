import { useState } from "react";
import { isAddress } from "viem";
import { contractRoute } from "../domain/route";
import { useDeployment } from "../state/deployment";
import { navigate } from "../state/route";

export function OpenContract() {
  const chainId = useDeployment().chain.id;
  const [text, setText] = useState("");
  const address = text.trim();
  return (
    <form className="panel" onSubmit={(e) => {
      e.preventDefault();
      if (isAddress(address)) navigate(contractRoute(chainId, address));
    }}>
      <h2>Call a deployed contract</h2>
      <div className="row">
        <input value={text} onChange={(e) => setText(e.target.value)} spellCheck={false}
          placeholder="0x… address of a deployed contract" aria-label="Contract address" />
        <button type="submit" disabled={!isAddress(address)}>Open</button>
      </div>
    </form>
  );
}
