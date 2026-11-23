import { BaseError, type Hex, isHex } from "viem";

// A node puts revert data in its JSON-RPC error's `data` or `data.data`, and viem's contract
// errors keep it as `raw`.
function dataIn(e: unknown): Hex | null {
  const { raw, data } = e as { raw?: unknown; data?: unknown };
  const nested = (data as { data?: unknown } | null | undefined)?.data;
  return [raw, data, nested].find((d): d is Hex => isHex(d)) ?? null;
}

// Returns the revert data that `error` carries, or null when it carries none.
export function revertData(error: unknown): Hex | null {
  if (!(error instanceof BaseError)) return null;
  let found: Hex | null = null;
  error.walk((e) => (found = dataIn(e)) !== null);
  return found;
}
