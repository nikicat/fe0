// Links to transactions and accounts on a chain's block explorer.
import type { Hex } from "viem";
import { explorerUrl, type ExplorerTarget } from "../chain/chains";
import { useDeployment } from "../state/deployment";

// Links `text` to `target` on the block explorer of the page's deployment.
export function Explorer({ target, text }: { target: ExplorerTarget; text: string }) {
  const href = explorerUrl(useDeployment(), target);
  return <a href={href} target="_blank" rel="noopener">{text}</a>;
}

// Returns `hex` cut to its first and last four digits, such as `0x1234…abcd`.
export const shortHex = (hex: Hex): string => `${hex.slice(0, 6)}…${hex.slice(-4)}`;
