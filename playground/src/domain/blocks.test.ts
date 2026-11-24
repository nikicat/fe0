import { expect, test } from "vitest";
import { blockRanges } from "./blocks";

test("blockRanges cuts a range into ranges of at most the size", () => {
  expect(blockRanges({ from: 10n, to: 34n }, 10n)).toEqual([
    { from: 10n, to: 19n }, { from: 20n, to: 29n }, { from: 30n, to: 34n },
  ]);
  expect(blockRanges({ from: 10n, to: 29n }, 10n)).toEqual([
    { from: 10n, to: 19n }, { from: 20n, to: 29n },
  ]);
  expect(blockRanges({ from: 7n, to: 7n }, 10n)).toEqual([{ from: 7n, to: 7n }]);
  expect(blockRanges({ from: 8n, to: 7n }, 10n)).toEqual([]);
});
