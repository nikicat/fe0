import { minOf } from "./generic";

// How many numbers `firstAtLeast` probes at once.
const PROBES = 8n;

// The numbers from `from` up to `end`, which is excluded.
export interface Interval {
  from: bigint;
  end: bigint;
}

// Returns the least `n` in `interval` for which `value(n)` is at least `target`, or its `end`
// when there is none. `value` must not decrease as `n` grows. The search takes about
// log(end - from) / log(PROBES) rounds of parallel calls to `value`.
export async function firstAtLeast({ from, end }: Interval, target: bigint,
  value: (n: bigint) => Promise<bigint>): Promise<bigint> {
  let lo = from;
  let hi = end;
  // The answer is in [lo, hi]: hi when no number in [lo, hi) reaches the target.
  while (lo < hi) {
    const span = hi - lo;
    const count = minOf(span, PROBES);
    const probes = Array.from({ length: Number(count) },
      (_, i) => lo + span * BigInt(i) / count);
    const values = await Promise.all(probes.map(value));
    const i = values.findIndex((v) => v >= target);
    if (span <= PROBES) return i < 0 ? hi : probes[i]!;
    if (i === 0) return lo;
    if (i < 0) {
      lo = probes[probes.length - 1]! + 1n;
    } else {
      lo = probes[i - 1]! + 1n;
      hi = probes[i]!;
    }
  }
  return lo;
}
