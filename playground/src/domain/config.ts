// tools/playground.py writes these types' values into src/config.ts from the repository
// (docs/adr/0032, "Configuration").
import type { Address } from "viem";
import type { Source } from "./source";

// The id of a chain, as EIP-155 numbers it.
export type ChainId = number & { readonly __brand: "ChainId" };

// An absolute URL. See tools/deploy.py, `Url`.
export type Url = string & { readonly __brand: "Url" };

// See tools/deploy.py, `Currency`.
export interface Currency {
  name: string;
  symbol: string;
  decimals: number;
}

// See tools/deploy.py, `Chain`.
export interface Chain {
  id: ChainId;
  name: string;
  rpc: Url;
  explorer: Url;
  currency: Currency;
  l1Blocks: boolean;
  logRange: number;
}

// A contract that this repository deployed, with its page on Sourcify, which shows whether
// Sourcify verified its source (docs/adr/0033-verify-on-sourcify.md).
export interface Verified {
  address: Address;
  sourcify: Url;
}

// One deployment that a page works on, which the route picks (docs/adr/0032, "Deployment").
// Its Compiler is the one of this repository's latest release.
export interface Deployed {
  chain: Chain;
  compiler: Verified;
  registry: Verified;
}

// An error code as the native CLI prints it, such as `N014`, with its message.
export interface Message {
  code: string;
  text: string;
}

export interface Config {
  repo: Url;
  deployments: Deployed[];
  // CreateX, through which Registry creates each contract, at the same address on every chain
  // that has it (docs/adr/0031-deployment-registry.md, "Deploying").
  createx: Address;
  messages: Record<string, Message>;
  // The `.fe` files directly in corpus/, by name.
  examples: Record<string, Source>;
  // The name of the example that the page opens with.
  start: string;
}

// `T` as JSON holds it: each branded value as its base type.
type Unbranded<T> =
  T extends { readonly __brand: unknown }
    ? T extends string ? string : T extends number ? number : T
    : T extends object ? { [K in keyof T]: Unbranded<T[K]> } : T;

// Returns `json` with its brands. tools/playground.py takes each branded value from the
// repository, so config.ts is the edge where the page trusts them.
export const branded = (json: Unbranded<Config>): Config => json as Config;

// The code of a `CompileError`, which keys `Config.messages`.
export type ErrorCode = bigint & { readonly __brand: "ErrorCode" };
