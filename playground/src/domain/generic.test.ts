import { expect, test } from "vitest";
import { Listeners, groupByValue, maxOf, memoize, memoizeSync, minOf } from "./generic";

test("minOf and maxOf give the least and the greatest value", () => {
  expect(minOf(3n)).toBe(3n);
  expect(minOf(3n, -1n, 7n)).toBe(-1n);
  expect(maxOf(3n, -1n, 7n)).toBe(7n);
});

test("groupByValue gathers the keys of each value", () => {
  const map = new Map([["a", 1], ["b", 2], ["c", 1]]);
  expect([...groupByValue(map)]).toEqual([[1, ["a", "c"]], [2, ["b"]]]);
});

test("memoize computes each argument once", async () => {
  let calls = 0;
  const double = memoize(async (n: number) => {
    calls++;
    return n * 2;
  });
  expect(await Promise.all([double(2), double(2), double(3)])).toEqual([4, 4, 6]);
  expect(await double(2)).toBe(4);
  expect(calls).toBe(2);
});

test("memoize tries again after a rejection", async () => {
  let calls = 0;
  const flaky = memoize(async (n: number) => {
    if (++calls === 1) throw new Error("down");
    return n;
  });
  await expect(flaky(1)).rejects.toThrow("down");
  expect(await flaky(1)).toBe(1);
  expect(calls).toBe(2);
});

test("Listeners calls each listener until it is removed", () => {
  const listeners = new Listeners();
  const calls: string[] = [];
  const removeA = listeners.subscribe(() => calls.push("a"));
  listeners.subscribe(() => calls.push("b"));
  listeners.notify();
  removeA();
  listeners.notify();
  expect(calls).toEqual(["a", "b", "b"]);
});

test("memoizeSync computes each argument once", () => {
  let calls = 0;
  const box = memoizeSync((n: number) => {
    calls++;
    return { n };
  });
  expect(box(2)).toBe(box(2));
  expect(box(3).n).toBe(3);
  expect(calls).toBe(2);
});
