// Reads from the chain, cached by TanStack Query, with registry records also kept in
// localStorage (docs/adr/0032, "Libraries").
import { QueryClient, skipToken, useQuery, useQueryClient } from "@tanstack/react-query";
import { RecordCache } from "./records";
import { useEffect, useMemo, useState } from "react";
import type { Address } from "viem";
import { publicClient } from "../chain/chains";
import { Compiler } from "../chain/compiler";
import { contractState, foundContract } from "../chain/contract";
import { type Recorded, Registry } from "../chain/registry";
import { type Failure, failureOf } from "../chain/failure";
import type { DeployCode } from "../domain/createx";
import type { ListCursor } from "../domain/registryList";
import type { Program } from "../domain/source";
import { useDeployment } from "./deployment";

// How long the page waits after an edit before it compiles, in milliseconds.
const COMPILE_DELAY = 500;

// Returns `value` once it has stayed the same for `delay` milliseconds.
function useSettled<T>(value: T, delay: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return settled;
}

// The state of the compile of the editor's program.
export type CompileView =
  // TanStack Query holds the compile back until the browser is online again.
  | { kind: "paused" }
  | { kind: "pending" }
  | { kind: "failed"; failure: Failure }
  // `gas` is null until its estimate returns, or when the estimate fails.
  | { kind: "compiled"; code: DeployCode; gas: bigint | null };

// Compiles `program` on the deployment's Compiler, COMPILE_DELAY after it last changed, and
// returns the state of that compile. A compile of the same source is cached.
export function useCompile(program: Program): CompileView {
  const deployment = useDeployment();
  const settled = useSettled(program, COMPILE_DELAY);
  const compiler = useMemo(() => new Compiler(deployment), [deployment]);
  const key = [deployment.chain.id, deployment.compiler.address, settled.source];
  const result = useQuery({
    queryKey: ["compile", ...key],
    queryFn: () => compiler.compile(settled),
    staleTime: Infinity,
  });
  const gas = useQuery({
    queryKey: ["compileGas", ...key],
    queryFn: () => compiler.compileGas(settled),
    enabled: result.isSuccess,
    staleTime: Infinity,
  });
  if (settled !== program || result.isFetching) return { kind: "pending" };
  if (result.isError) return { kind: "failed", failure: failureOf(result.error, settled) };
  if (result.isSuccess) {
    return { kind: "compiled", code: result.data, gas: gas.data ?? null };
  }
  return { kind: "paused" };
}

// Returns the stale time of a read whose value never changes once found. A found value stays
// cached for good. A missing one is read again when a component that shows it mounts.
const staleUntilFound = (found: boolean): number => found ? Infinity : 0;

// Reads the code size and `version()` of the contract at `address`, or nothing while `address`
// is null. Returns the read's query and the contract it found, which is null until it finds
// one. A contract's code never changes, so the read follows staleUntilFound.
export function useContract(address: Address | null) {
  const deployed = useDeployment();
  const query = useQuery({
    queryKey: ["contract", deployed.chain.id, address],
    queryFn: address === null ? skipToken
      : () => contractState(publicClient(deployed), address),
    staleTime: (q) => staleUntilFound(foundContract(q.state.data) !== null),
  });
  return { query, found: foundContract(query.data) };
}

// Reads the page at `cursor` from the registry.
export function useRegistryPage(cursor: ListCursor) {
  const deployed = useDeployment();
  return useQuery({
    queryKey: ["registryPage", deployed.chain.id, cursor.account, cursor.skip.toString()],
    queryFn: () => Registry.of(deployed).page(cursor),
  });
}

// Builds the page's QueryClient. A failed read is shown, not retried.
export function newQueryClient(): QueryClient {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryDefaults(...RecordCache.defaults);
  return client;
}

// Returns the RecordCache of the deployment's chain.
function useRecordCache(): RecordCache {
  return new RecordCache(useQueryClient(), useDeployment().chain.id);
}

// Reads what the registry recorded of each of `addresses`. The map has an entry for each
// address, which is null when the registry has no record of it. A record never changes, so the
// read follows staleUntilFound.
export function useRecords(addresses: readonly Address[]) {
  const deployed = useDeployment();
  const cache = useRecordCache();
  const cached = (a: Address) => cache.get(a);
  const all = (): Map<Address, Recorded | null> | undefined => {
    const records = addresses.map(cached);
    return records.every((r) => r !== undefined)
      ? new Map(addresses.map((a, i) => [a, records[i]!])) : undefined;
  };
  return useQuery({
    queryKey: ["records", deployed.chain.id, ...addresses],
    queryFn: async () => {
      const missing = addresses.filter((a) => cached(a) === undefined);
      const read = missing.length === 0 ? new Map<Address, Recorded | null>()
        : await Registry.of(deployed).records(missing);
      for (const [a, r] of read) if (r !== null) cache.remember(a, r);
      return new Map(addresses.map((a) => [a, cached(a) ?? null]));
    },
    initialData: all,
    enabled: addresses.length > 0,
    staleTime: (q) => staleUntilFound(
      q.state.data !== undefined && [...q.state.data.values()].every((r) => r !== null)),
  });
}

// The state of the read of the registry's record of a contract.
export type RecordView =
  | { kind: "reading" }
  | { kind: "failed"; error: Error }
  | { kind: "recorded"; record: Recorded }
  // The registry lacks the contract, by a read that has finished.
  | { kind: "unrecorded" };

// Reads what the registry recorded of `address`, as useRecords does, and returns the state of
// that read.
export function useRecord(address: Address): RecordView {
  const records = useRecords([address]);
  const record = records.data?.get(address) ?? null;
  if (record !== null) return { kind: "recorded", record };
  if (records.isError) return { kind: "failed", error: records.error };
  if (records.isSuccess && !records.isFetching) return { kind: "unrecorded" };
  return { kind: "reading" };
}

// Returns RecordCache.remember on the deployment's chain.
export function useRememberRecord() {
  const cache = useRecordCache();
  return (address: Address, record: Recorded) => cache.remember(address, record);
}
