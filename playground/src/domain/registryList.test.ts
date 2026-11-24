import { describe, expect, it } from "vitest";
import { ListCursor, type ListPage } from "./registryList";

const all = (skip: bigint) => new ListCursor(null, skip);
// The page of `cursor` in a list of `total` contracts, with no items.
const pageOf = (cursor: ListCursor, total: bigint): ListPage => cursor.page(total, []);

describe("ListCursor", () => {
  it("covers the newest 20 contracts of the list on its first page", () => {
    expect(all(0n).window(45n)).toEqual({ start: 25n, count: 20n });
  });

  it("covers what is left on the last page", () => {
    expect(all(40n).window(45n)).toEqual({ start: 0n, count: 5n });
  });

  it("covers nothing past the end of the list", () => {
    expect(all(60n).window(45n)).toEqual({ start: 0n, count: 0n });
  });

  it("gives a page with its items newest first", () => {
    const [a, b] = ["0x0000000000000000000000000000000000000001",
      "0x0000000000000000000000000000000000000002"] as const;
    expect(all(0n).page(2n, [a, b]).items).toEqual([b, a]);
  });
});

describe("ListPage", () => {
  it("shows the positions of its contracts", () => {
    expect(pageOf(all(0n), 45n).shown()).toEqual({ newest: 1n, oldest: 20n });
    expect(pageOf(all(40n), 45n).shown()).toEqual({ newest: 41n, oldest: 45n });
  });

  it("pages newer down to the first page, and older up to the last", () => {
    expect(pageOf(all(0n), 45n).newer()).toBeNull();
    expect(pageOf(all(30n), 45n).newer()?.skip).toBe(10n);
    expect(pageOf(all(10n), 45n).newer()?.skip).toBe(0n);
    expect(pageOf(all(20n), 45n).older()?.skip).toBe(40n);
    expect(pageOf(all(20n), 40n).older()).toBeNull();
    expect(pageOf(all(40n), 45n).older()).toBeNull();
  });

  it("keeps its account across pages", () => {
    const account = "0x0000000000000000000000000000000000000001";
    expect(pageOf(new ListCursor(account), 45n).older()?.account).toBe(account);
  });
});
