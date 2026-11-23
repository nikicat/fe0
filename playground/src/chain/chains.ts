// wagmi holds every chain in config.ts at once, so the page can switch between them
// (docs/adr/0032, "Libraries").
import {
  type Address, type Chain as ViemChain, type Hex, type PublicClient, defineChain,
} from "viem";
import { type Connector, http, createConfig } from "wagmi";
import { getPublicClient } from "wagmi/actions";
import { injected } from "wagmi/connectors";
import type { Deployed } from "../domain/config";
import { deployments } from "./deployments";

// Returns the viem chain of `deployed`.
const viemChain = ({ chain }: Deployed): ViemChain =>
  defineChain({
    id: chain.id,
    name: chain.name,
    nativeCurrency: chain.currency,
    rpcUrls: { default: { http: [chain.rpc] } },
    blockExplorers: {
      default: { name: new URL(chain.explorer).hostname, url: chain.explorer },
    },
  });

const [first, ...rest] = deployments;
const chains = [viemChain(first), ...rest.map(viemChain)] as const;

export const wagmiConfig = createConfig({
  chains,
  connectors: [injected()],
  transports: Object.fromEntries(chains.map((c) => [c.id, http()])),
});

// The connector that wagmiConfig sends transactions through.
export const browserWallet: Connector = wagmiConfig.connectors[0]!;

// Returns the client that reads from the chain of `deployed` through its RPC endpoint.
export function publicClient({ chain }: Deployed): PublicClient {
  const client = getPublicClient(wagmiConfig, { chainId: chain.id });
  // wagmiConfig has the chain of every deployment.
  if (!client) throw new Error(`wagmiConfig lacks the chain ${chain.id}.`);
  return client;
}

// What an explorer link points to: a transaction or an account.
export type ExplorerTarget = { tx: Hex } | { address: Address };

// Returns the URL of `target` on the block explorer of the chain of `deployed`.
export function explorerUrl({ chain }: Deployed, target: ExplorerTarget): string {
  const path = "tx" in target ? `tx/${target.tx}` : `address/${target.address}`;
  return `${chain.explorer}/${path}`;
}
