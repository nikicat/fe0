// A long hex value, such as an address, shortened by CSS so that a copy gets the whole value
// (docs/adr/0032-playground-architecture.md, "Hex values").
import type { Hex } from "viem";

// How many digits stay visible after the cut. The head's width is set by .hex-head in
// style.css, and the two make the cut.
const TAIL = 4;

export function HexText({ value }: { value: Hex }) {
  return (
    <span className="hex" title={value}>
      <span className="hex-head">{value.slice(0, -TAIL)}</span>
      <span className="hex-tail">{value.slice(-TAIL)}</span>
    </span>
  );
}
