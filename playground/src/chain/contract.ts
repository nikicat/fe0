// Reads of any contract. The page reads `version()` from any contract, with a signature that it
// owns (docs/adr/0032, "Contract versions").
import {
  type Address, BaseError, ContractFunctionRevertedError, ContractFunctionZeroDataError,
  type PublicClient, parseAbi, size,
} from "viem";

const versionAbi = parseAbi(["function version() view returns (string)"]);

// What the chain holds at an address: no code, or a contract of `size` bytes, with the string
// that `version()` returns, or null when the contract has no `version()`.
export type ContractState =
  | { kind: "empty" }
  | { kind: "contract"; size: number; version: string | null };

// A contract that the chain holds.
export type FoundContract = Extract<ContractState, { kind: "contract" }>;

export const foundContract = (state: ContractState | undefined): FoundContract | null =>
  state?.kind === "contract" ? state : null;

// Returns the size in bytes of the code at `address`, which is 0 when it holds no contract.
export async function codeSize(client: PublicClient, address: Address): Promise<number> {
  const code = await client.getCode({ address });
  return code ? size(code) : 0;
}

// Returns the string that `version()` returns at `address`, or null when the call reverts or
// returns no data. Errors with viem's error when the read fails for another reason.
async function contractVersion(client: PublicClient, address: Address): Promise<string | null> {
  try {
    return await client.readContract({ address, abi: versionAbi, functionName: "version" });
  } catch (e) {
    const absent = e instanceof BaseError && e.walk((c) =>
      c instanceof ContractFunctionRevertedError || c instanceof ContractFunctionZeroDataError);
    if (absent) return null;
    throw e;
  }
}

// Returns what the chain holds at `address`. Errors with viem's error when a read fails.
export async function contractState(client: PublicClient,
  address: Address): Promise<ContractState> {
  const size = await codeSize(client, address);
  if (size === 0) return { kind: "empty" };
  return { kind: "contract", size, version: await contractVersion(client, address) };
}
