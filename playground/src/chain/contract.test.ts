import {
  type Address, ContractFunctionExecutionError, ContractFunctionRevertedError,
  ContractFunctionZeroDataError, HttpRequestError, type PublicClient, parseAbi,
} from "viem";
import { expect, test } from "vitest";
import { contractState } from "./contract";

const address: Address = "0x00000000000000000000000000000000000000aa";
const abi = parseAbi(["function version() view returns (string)"]);
const functionName = "version";

// A client whose contract has 3 bytes of code and whose `version()` read does `read`.
const client = (read: () => Promise<string>) =>
  ({ getCode: async () => "0x600000", readContract: read }) as unknown as PublicClient;

const failed = (cause: Error) =>
  new ContractFunctionExecutionError(cause as never, { abi, functionName, args: [] });

test("a contract whose version() reverts or returns nothing has no version", async () => {
  const causes = [
    new ContractFunctionRevertedError({ abi, functionName, data: "0x" }),
    new ContractFunctionZeroDataError({ functionName }),
  ];
  for (const cause of causes) {
    const state = await contractState(client(() => Promise.reject(failed(cause))), address);
    expect(state).toEqual({ kind: "contract", size: 3, version: null });
  }
});

test("a failed RPC request is an error, not a missing version", async () => {
  const cause = new HttpRequestError({ url: "http://rpc", status: 429 });
  const error = failed(cause);
  await expect(contractState(client(() => Promise.reject(error)), address)).rejects.toBe(error);
});

test("an address without code holds no contract", async () => {
  const empty = { getCode: async () => undefined } as unknown as PublicClient;
  expect(await contractState(empty, address)).toEqual({ kind: "empty" });
});
