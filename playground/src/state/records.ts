// The registry's records, kept for the page's life and across visits (docs/adr/0032,
// "Libraries"). When the browser refuses storage, as in a private window, the page reads each
// record from the chain on each visit.
import type { QueryClient } from "@tanstack/react-query";
import type { Address } from "viem";
import type { Recorded } from "../chain/registry";
import type { ChainId } from "../domain/config";
import type { Source } from "../domain/source";

const KEY = "record";

// The identity of a record: its chain and its checksummed address. The page caches a record
// under it, both for this visit and in localStorage.
type RecordId = string & { readonly __brand: "RecordId" };

// A record as JSON holds it: the block as a decimal string.
type Stored = Omit<Recorded, "block"> & { block: string };

// The registry's records on the chain `chainId`. Each record has one entry, which every view
// that shows it shares.
export class RecordCache {
  // The query defaults that keep each record for the page's life. No component reads a
  // record's own key, so TanStack Query would otherwise drop it after a few minutes.
  static readonly defaults = [[KEY], { gcTime: Infinity }] as const;

  constructor(private readonly client: QueryClient, private readonly chainId: ChainId) {}

  // Returns the record of `address`, or undefined when neither this visit nor localStorage
  // holds it.
  get(address: Address): Recorded | undefined {
    return this.client.getQueryData<Recorded>(this.#queryKey(address)) ?? this.#load(address);
  }

  // Keeps `record` as the record of `address`, for this visit and in localStorage.
  remember(address: Address, record: Recorded): void {
    this.client.setQueryData(this.#queryKey(address), record);
    this.#store(address, record);
  }

  #id(address: Address): RecordId {
    return `${this.chainId}.${address}` as RecordId;
  }

  #queryKey(address: Address) {
    return [KEY, this.#id(address)];
  }

  #storageKey(address: Address): string {
    return `fe0.record.v1.${this.#id(address)}`;
  }

  #load(address: Address): Recorded | undefined {
    try {
      const text = localStorage.getItem(this.#storageKey(address));
      if (text === null) return undefined;
      const stored = JSON.parse(text) as Stored;
      return { ...stored, source: stored.source as Source, block: BigInt(stored.block) };
    } catch {
      return undefined;
    }
  }

  #store(address: Address, record: Recorded): void {
    try {
      const stored: Stored = { ...record, block: record.block.toString() };
      localStorage.setItem(this.#storageKey(address), JSON.stringify(stored));
    } catch {
      // A refused storage: see the module doc.
    }
  }
}
