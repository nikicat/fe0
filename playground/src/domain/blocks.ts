import { minOf } from "./generic";

// The blocks from `from` to `to`, both included.
export interface BlockRange {
  from: bigint;
  to: bigint;
}

// Returns `range` cut into ranges of at most `size` blocks, in order.
export function blockRanges(range: BlockRange, size: bigint): BlockRange[] {
  const ranges: BlockRange[] = [];
  for (let from = range.from; from <= range.to; from += size) {
    ranges.push({ from, to: minOf(from + size - 1n, range.to) });
  }
  return ranges;
}
