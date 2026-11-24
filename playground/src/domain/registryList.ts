// The pages of the registry's lists of contracts, newest first
// (docs/adr/0031-deployment-registry.md, "Reading").
import type { Address } from "viem";
import { maxOf } from "./generic";

// How many contracts a page holds.
const PAGE_SIZE = 20n;

// The contracts that a page covers in the registry's order, oldest first: `count` of them from
// index `start`.
export interface Window {
  start: bigint;
  count: bigint;
}

// A place in a registry list: the page after the newest `skip` contracts. The list holds every
// contract that the registry recorded when `account` is null, and only those that `account`
// deployed through the registry otherwise.
export class ListCursor {
  constructor(readonly account: Address | null, readonly skip: bigint = 0n) {}

  // Returns the contracts of this page in a list of `total` contracts.
  window(total: bigint): Window {
    const end = maxOf(total - this.skip, 0n);
    const start = maxOf(end - PAGE_SIZE, 0n);
    return { start, count: end - start };
  }

  // Returns this page of a list of `total` contracts, from the contracts of its window in the
  // registry's order.
  page(total: bigint, window: readonly Address[]): ListPage {
    return new ListPage(this, total, [...window].reverse());
  }
}

// One page of a registry list as read: its `items`, newest first, and the length of the list.
export class ListPage {
  constructor(readonly cursor: ListCursor, readonly total: bigint,
    readonly items: readonly Address[]) {}

  // Returns the page before this one, or null on the first page.
  newer(): ListCursor | null {
    const { account, skip } = this.cursor;
    return skip === 0n ? null : new ListCursor(account, maxOf(skip - PAGE_SIZE, 0n));
  }

  // Returns the page after this one, or null on the last page.
  older(): ListCursor | null {
    const last = this.cursor.skip + PAGE_SIZE;
    return last < this.total ? new ListCursor(this.cursor.account, last) : null;
  }

  // Returns the positions, counted from 1 at the newest, of the newest and oldest contracts of
  // this page.
  shown(): { newest: bigint; oldest: bigint } {
    const { skip } = this.cursor;
    return { newest: skip + 1n, oldest: skip + this.cursor.window(this.total).count };
  }
}
