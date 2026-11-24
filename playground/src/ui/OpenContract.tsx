import { useState } from "react";
import { isAddress } from "viem";
import { useContractLink } from "../state/route";

export function OpenContract() {
  const contract = useContractLink();
  const [text, setText] = useState("");
  const address = text.trim();
  return (
    <form className="card" aria-label="Open a contract" onSubmit={(e) => {
      e.preventDefault();
      if (isAddress(address)) contract.open(address);
    }}>
      <h2>Open a contract</h2>
      <div className="inline">
        <input value={text} onChange={(e) => setText(e.target.value)} spellCheck={false}
          placeholder="0x… address" aria-label="Contract address" />
        <button type="submit" disabled={!isAddress(address)}>Open</button>
      </div>
    </form>
  );
}
