// Until the registry exists, a contract's page takes its call forms from the program in the
// editor (docs/adr/0032).
import type { Address } from "viem";
import { failureOf } from "../chain/failure";
import type { ChainId } from "../domain/config";
import type { Outline } from "../domain/outline";
import { useDeployment } from "../state/deployment";
import { navigate } from "../state/route";
import { useContract } from "../state/queries";
import { CallForms } from "./CallForms";
import { Explorer } from "./Explorer";
import { FailureText, StatusText } from "./Status";

// What the chain holds at `address`: its code size and `version()`, or why they are unknown.
function ContractStatus({ address }: { address: Address }) {
  const contract = useContract(useDeployment(), address);
  if (contract.isPending) return <StatusText tone="info">Reading the contract…</StatusText>;
  if (contract.isError) {
    const failure = failureOf(contract.error, null);
    return <StatusText tone="err"><FailureText failure={failure} /></StatusText>;
  }
  if (contract.data.kind === "empty") {
    return <StatusText tone="err">No contract is at this address.</StatusText>;
  }
  const { size, version } = contract.data;
  return (
    <StatusText tone="ok">
      {size.toLocaleString()} bytes of code
      {version !== null && `, version() returns "${version}"`}.
    </StatusText>
  );
}

function DeployAnother() {
  return (
    <button type="button" onClick={() => navigate({ page: "editor", source: null })}>
      Deploy another
    </button>
  );
}

// The page of the contract at `address` on the page's deployment.
export function ContractPage({ address, outline }: { address: Address; outline: Outline }) {
  const deployed = useDeployment();
  return (
    <>
      <div className="panel">
        <h2>Contract</h2>
        <p className="address-line">
          <Explorer target={{ address }} text={address} /> on {deployed.chain.name}
        </p>
        <ContractStatus address={address} />
        <DeployAnother />
      </div>
      <div className="panel">
        <h2>Call and send</h2>
        <p className="hint">A call is a free <code>eth_call</code>. A send is a transaction from
          your wallet. There is one form for each message that the program in the editor
          receives (its <code>msg</code> variants), guessed from the source. A wrong guess, or
          a program other than the contract's, sends calldata that the contract does not expect,
          and it reverts.</p>
        <CallForms outline={outline} address={address} />
      </div>
    </>
  );
}

// The page of a contract on a chain that config.ts lacks, which the page can neither read
// nor call.
export function UnknownChainPage({ chainId, address }: { chainId: ChainId; address: Address }) {
  return (
    <div className="panel">
      <h2>Contract</h2>
      <p className="address-line">{address}</p>
      <StatusText tone="err">The page knows no chain {chainId}.</StatusText>
      <DeployAnother />
    </div>
  );
}
