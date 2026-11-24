// Contracts link to Sourcify, which shows their Fe source, and not to the block explorer
// (docs/adr/0032-playground-architecture.md, "Links").
import type { Verified } from "../domain/config";
import { HexText } from "./HexText";

// Links the contract `verified` to its page on Sourcify.
export function SourcifyLink({ verified }: { verified: Verified }) {
  return <a href={verified.sourcify}><HexText value={verified.address} /> on Sourcify</a>;
}
