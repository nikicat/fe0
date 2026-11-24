// Only transactions link to the block explorer; contracts link to Sourcify
// (docs/adr/0032-playground-architecture.md, "Links").
import type { Hex } from "viem";
import { txUrl } from "../chain/chains";
import { useDeployment } from "../state/deployment";
import { HexText } from "./HexText";

// Links the transaction `hash` to the block explorer of the current deployment's chain.
export function TxLink({ hash }: { hash: Hex }) {
  return <a href={txUrl(useDeployment(), hash)} target="_blank" rel="noopener">
    <HexText value={hash} /></a>;
}
