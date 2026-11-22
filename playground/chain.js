// The chain that Compiler runs on.
import { createPublicClient, defineChain, http } from "./viem.js";
import { escape } from "./dom.js";

// Returns the HTML of a link to `path` on the block explorer of `chain`, showing `text`.
export const explorerLink = (chain, path, text) =>
  `<a href="${chain.blockExplorers.default.url}/${escape(path)}" target="_blank"` +
  ` rel="noopener">${escape(text)}</a>`;

// Returns a public client of the chain that `data.chain` describes. All Arbitrum chains pay
// gas in ETH.
export function clientOf(data) {
  const { id, name, rpc, explorer } = data.chain;
  const chain = defineChain({
    id,
    name,
    nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
    rpcUrls: { default: { http: [rpc] } },
    blockExplorers: { default: { name: new URL(explorer).hostname, url: explorer } },
  });
  return createPublicClient({ chain, transport: http(rpc) });
}
