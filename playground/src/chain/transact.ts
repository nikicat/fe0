// Transactions from the browser wallet.
import type { Address, Hex } from "viem";
import {
  connect, getConnection, sendTransaction, switchChain,
  waitForTransactionReceipt,
} from "wagmi/actions";
import { ProviderNotFoundError } from "wagmi";
import type { ChainId, Deployed } from "../domain/config";
import { browserWallet, publicClient, wagmiConfig } from "./chains";

// How long the page waits for a sent transaction to be mined, in milliseconds.
const RECEIPT_TIMEOUT = 120_000;

export interface Tx {
  to: Address;
  data: Hex;
}

// The steps of a transaction from the wallet until it is mined.
export type Progress =
  | { step: "approve" }
  | { step: "sent"; hash: Hex };

// A transaction that was mined and succeeded.
export interface Mined {
  hash: Hex;
  gasUsed: bigint;
}

// Connects the browser wallet when it is not connected, and returns its account. Errors with
// Error when there is no browser wallet, or with viem's UserRejectedRequestError when the user
// rejects the connection.
export async function connectWallet(): Promise<Address> {
  const now = getConnection(wagmiConfig);
  if (now.address) return now.address;
  try {
    const { accounts } = await connect(wagmiConfig, { connector: browserWallet });
    return accounts[0]!;
  } catch (e) {
    if (!(e instanceof ProviderNotFoundError)) throw e;
    throw new Error(
      "No browser wallet found. Install one, such as MetaMask, to deploy and send.");
  }
}

// Connects the browser wallet and switches it to the chain `chainId`, adding the chain when
// the wallet lacks it, and returns its account. Errors as `connectWallet` does, or with the
// wallet's error when it refuses the switch.
async function walletOn(chainId: ChainId): Promise<Address> {
  const from = await connectWallet();
  if (getConnection(wagmiConfig).chainId !== chainId) {
    await switchChain(wagmiConfig, { chainId });
  }
  return from;
}

// Returns the return data of `tx` by `eth_call` on the chain of `deployed`, sent from `from`
// when given, or `0x` when it returns none.
export async function callTx(deployed: Deployed, tx: Tx, from?: Address): Promise<Hex> {
  const { data } = await publicClient(deployed).call({ account: from, ...tx });
  return data ?? "0x";
}

// Sends `tx` from the wallet on the chain of `deployed` and reports each Progress. Returns the
// simulated return data and the mined transaction. Errors as `walletOn` does, with a viem
// error that carries the revert data when the simulation reverts, or with Error when the
// transaction fails or is not mined in RECEIPT_TIMEOUT.
export async function transact(deployed: Deployed, tx: Tx, progress: (p: Progress) => void):
  Promise<{ result: Hex; mined: Mined }> {
  const from = await walletOn(deployed.chain.id);
  const result = await callTx(deployed, tx, from);
  // wagmi picks the chain whose id has the type of `chainId`, and its chains' ids are numbers.
  const chainId: number = deployed.chain.id;
  progress({ step: "approve" });
  const hash = await sendTransaction(wagmiConfig, { chainId, account: from, ...tx });
  progress({ step: "sent", hash });
  const receipt = await waitForTransactionReceipt(wagmiConfig,
    { chainId, hash, timeout: RECEIPT_TIMEOUT });
  if (receipt.status !== "success") throw new Error(`The transaction ${hash} failed.`);
  return { result, mined: { hash, gasUsed: receipt.gasUsed } };
}
