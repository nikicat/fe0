// The tests' anvil fork of the chain that the page opens on.
import { defaultDeployment } from "../src/chain/deployments";

export const { chain } = defaultDeployment;
export const FORK = new URL("http://127.0.0.1:8547/");
// The fork starts at the chain's latest block, since its public RPC endpoint keeps no older
// state.
export const FORK_COMMAND =
  `anvil --fork-url ${chain.rpc} --host ${FORK.hostname} --port ${FORK.port} --silent`;
