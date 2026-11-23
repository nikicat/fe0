// Reads from the chain, cached by TanStack Query.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import type { Address } from "viem";
import { publicClient } from "../chain/chains";
import { Compiler, type DeployCode } from "../chain/compiler";
import { contractState } from "../chain/contract";
import { type Failure, failureOf } from "../chain/failure";
import type { Deployed } from "../domain/config";
import type { Source } from "../domain/source";

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

// Compiles `source` on the Compiler of `deployment`, COMPILE_DELAY after it last changed, and
// returns the state of that compile. A compile of the same source is cached.
export function useCompile(deployment: Deployed, source: Source): CompileView {
  const settled = useSettled(source, COMPILE_DELAY);
  const compiler = useMemo(() => new Compiler(deployment), [deployment]);
  const key = [deployment.chain.id, deployment.compiler, settled];
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
  if (settled !== source || result.isFetching) return { kind: "pending" };
  if (result.isError) return { kind: "failed", failure: failureOf(result.error, settled) };
  if (result.isSuccess) {
    return { kind: "compiled", code: result.data, gas: gas.data ?? null };
  }
  return { kind: "paused" };
}

// Reads the code size and `version()` of the contract at `address` on the chain of `deployed`.
export function useContract(deployed: Deployed, address: Address) {
  return useQuery({
    queryKey: ["contract", deployed.chain.id, address],
    queryFn: () => contractState(publicClient(deployed), address),
  });
}
