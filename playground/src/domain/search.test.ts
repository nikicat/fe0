import { expect, test } from "vitest";
import { firstAtLeast } from "./search";

// The value of `n` is `n / 3`, rounded down: 0, 0, 0, 1, 1, 1, 2, …
const value = async (n: bigint) => n / 3n;

test("firstAtLeast finds the first number whose value reaches the target", async () => {
  for (const end of [1n, 7n, 8n, 9n, 1000n, 123_457n]) {
    for (const target of [0n, 1n, 2n, end / 6n, end / 3n - 1n]) {
      if (target < 0n || target * 3n >= end) continue;
      expect(await firstAtLeast({ from: 0n, end }, target, value), `${end} ${target}`)
        .toBe(target * 3n);
    }
  }
});

test("firstAtLeast returns the end when no number reaches the target", async () => {
  expect(await firstAtLeast({ from: 0n, end: 1000n }, 1000n, value)).toBe(1000n);
  expect(await firstAtLeast({ from: 5n, end: 5n }, 0n, value)).toBe(5n);
});

test("firstAtLeast probes a few numbers per round", async () => {
  let probes = 0;
  await firstAtLeast({ from: 0n, end: 500_000_000n }, 26_000_000n, async (n) => {
    probes++;
    return n / 20n;
  });
  expect(probes).toBeLessThanOrEqual(8 * 11);
});
