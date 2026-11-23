import { Compiler } from "../chain/compiler";
import { encodeArgs } from "../domain/abi";
import type { Outline } from "../domain/outline";
import { contractRoute } from "../domain/route";
import type { Source } from "../domain/source";
import { useDeployment } from "../state/deployment";
import { navigate } from "../state/route";
import { INIT_FORM, useFieldTexts } from "../state/store";
import { isRunning, useAction } from "../state/transaction";
import { Fields } from "./Fields";
import { StatusLine } from "./Status";
import { WalletButton } from "./WalletButton";

export function DeployPanel({ source, outline }: { source: Source; outline: Outline }) {
  const deployment = useDeployment();
  const texts = useFieldTexts(INIT_FORM, outline.init);
  const { status, run } = useAction();

  const deploy = () => run("Simulating the deployment…", async (progress) => {
    const args = encodeArgs(texts);
    const address = await new Compiler(deployment).deploy(source, args, progress);
    navigate(contractRoute(deployment.chain.id, address));
    return `Deployed at ${address}.`;
  }, source);

  return (
    <div className="panel">
      <h2>Deploy</h2>
      <p className="hint">Deploying sends <code>deploy(src, args)</code> to the compiler on
        chain, which compiles the program and creates the contract. <code>args</code> holds the
        values of the parameters of <code>init</code>, the contract's constructor, from the
        fields below. It costs gas, and the page asks your wallet to switch to the chain. The
        page then opens the address that the simulation gave. If someone else deploys through
        the compiler between the simulation and the transaction, that address holds their
        contract.</p>
      <Fields form={INIT_FORM} texts={texts} />
      <div className="row">
        <WalletButton />
        <button type="button" className="primary" onClick={deploy}
          disabled={isRunning(status)}>Deploy</button>
      </div>
      <StatusLine status={status} />
    </div>
  );
}
