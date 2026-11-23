// A page whose RPC requests go to the anvil fork, with a browser wallet that anvil signs for.
import { test as base } from "@playwright/test";
import { type Address, type Hex, numberToHex } from "viem";
import { chain, FORK } from "./fork";

// anvil's first account, which it funds and signs for.
const ACCOUNT: Address = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266";

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "*",
  "access-control-allow-methods": "POST, OPTIONS",
};

// An EIP-1193 provider as `window.ethereum`. It answers for the account and the chain itself,
// and sends every other request to the chain's RPC endpoint, which the fixture's `page.route`
// handler sends on to anvil.
function wallet({ account, chainId, rpc }: { account: Address; chainId: Hex; rpc: string }) {
  let id = 0;
  const own: Record<string, unknown> = {
    eth_requestAccounts: [account],
    eth_accounts: [account],
    eth_chainId: chainId,
    wallet_switchEthereumChain: null,
    wallet_addEthereumChain: null,
  };
  (window as unknown as { ethereum: unknown }).ethereum = {
    isMetaMask: false,
    on() {},
    removeListener() {},
    async request({ method, params }: { method: string; params?: unknown[] }) {
      if (method in own) return own[method];
      const r = await fetch(rpc, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", id: ++id, method, params: params ?? [] }),
      });
      const reply = await r.json();
      if (reply.error) throw Object.assign(new Error(reply.error.message), reply.error);
      return reply.result;
    },
  };
}

// Makes ACCOUNT a plain account on the fork. On Arbitrum One it carries an EIP-7702 delegation
// to code that a third party controls. Errors with anvil's message when anvil refuses.
async function clearDelegation(): Promise<void> {
  const r = await fetch(FORK, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(
      { jsonrpc: "2.0", id: 1, method: "anvil_setCode", params: [ACCOUNT, "0x"] }),
  });
  const reply = await r.json();
  if (reply.error) throw new Error(`anvil_setCode: ${reply.error.message}`);
}

export const test = base.extend({
  page: async ({ page }, use) => {
    await clearDelegation();
    await page.route(chain.rpc, async (route) => {
      if (route.request().method() === "OPTIONS") {
        await route.fulfill({ status: 204, headers: CORS });
        return;
      }
      const response = await route.fetch({ url: FORK.href });
      await route.fulfill({ response, headers: { ...response.headers(), ...CORS } });
    });
    await page.addInitScript(wallet,
      { account: ACCOUNT, chainId: numberToHex(chain.id), rpc: chain.rpc });
    await use(page);
    // A compile may still be in flight when a test ends.
    await page.unrouteAll({ behavior: "ignoreErrors" });
  },
});

export { expect } from "@playwright/test";
