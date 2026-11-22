// The browser wallet, which sends the page's transactions.
import { BaseError, createWalletClient, custom } from "./viem.js";
import { Status, setStatus } from "./dom.js";
import { explorerLink } from "./chain.js";

// How long the page waits for a sent transaction to be mined, in milliseconds.
const RECEIPT_TIMEOUT = 120_000;
// The error code of `wallet_switchEthereumChain` for a chain that the wallet does not know
// (EIP-3326).
const UNKNOWN_CHAIN = 4902;

// The browser wallet on the chain of the public client `client`, which simulates the wallet's
// transactions and waits for them.
export class Wallet {
  #client;
  #wallet;
  #connected;
  // The wallet's account, or null until it connects.
  #account = null;

  // Makes the wallet, which calls `connected` with the account when it first connects.
  constructor(client, connected) {
    this.#client = client;
    this.#wallet = window.ethereum
      ? createWalletClient({ chain: client.chain, transport: custom(window.ethereum) })
      : null;
    this.#connected = connected;
  }

  // Connects the browser wallet, switches it to the chain, and returns its account. Errors
  // with Error when there is no wallet, or when the user rejects a request.
  async account() {
    if (!this.#wallet) {
      throw new Error(
        "No browser wallet found. Install one, such as MetaMask, to deploy and send.");
    }
    if (!this.#account) {
      [this.#account] = await this.#wallet.requestAddresses();
      this.#connected(this.#account);
    }
    await this.#switchChain();
    return this.#account;
  }

  // Sends `tx` from the wallet, shows its progress in `out`, and returns what its simulation
  // returned. Errors as `account` does, with a viem error that carries the revert data when the
  // simulation reverts, and with Error when `tx` fails or is not mined in RECEIPT_TIMEOUT.
  async send(tx, out) {
    const full = { account: await this.account(), ...tx };
    const { data: result = "0x" } = await this.#client.call(full);
    setStatus(out, Status.busy, "Approve the transaction in your wallet…");
    const hash = await this.#wallet.sendTransaction(full);
    const link = explorerLink(this.#client.chain, `tx/${hash}`, `${hash.slice(0, 10)}…`);
    setStatus(out, Status.busy, `Sent ${link}. Waiting for it to be mined…`);
    const r = await this.#client.waitForTransactionReceipt({ hash, timeout: RECEIPT_TIMEOUT });
    if (r.status !== "success") throw new Error(`The transaction ${hash} failed.`);
    setStatus(out, Status.ok, `Mined ${link}, ${r.gasUsed.toLocaleString()} gas.`);
    return result;
  }

  // Switches the wallet to the chain, and adds the chain when the wallet does not know it.
  async #switchChain() {
    const { chain } = this.#client;
    if ((await this.#wallet.getChainId()) === chain.id) return;
    try {
      await this.#wallet.switchChain({ id: chain.id });
    } catch (e) {
      if (!(e instanceof BaseError && e.walk((c) => c.code === UNKNOWN_CHAIN))) throw e;
      await this.#wallet.addChain({ chain });
    }
  }
}
