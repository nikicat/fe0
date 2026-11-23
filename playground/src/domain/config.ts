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
}

// A Compiler that a release of this repository deployed on a chain. The page treats such
// Compilers as known (docs/adr/0032).
export interface Deployed {
  chain: Chain;
  compiler: Address;
  // Sourcify's page of the Compiler, which shows whether Sourcify verified its source
  // (docs/adr/0033-verify-on-sourcify.md).
  sourcify: Url;
}

// An error code as the native CLI prints it, such as `N014`, with its message.
export interface Message {
  code: string;
  text: string;
}

export interface Config {
  repo: Url;
  deployments: Deployed[];
  // Read with `cliMessage`.
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

// Returns the CLI's message for the error code `code`, or null when the CLI has none.
// `messages` is keyed by the code in decimal, as tools/playground.py writes it.
export const cliMessage = (messages: Config["messages"], code: ErrorCode): Message | null =>
  messages[code.toString()] ?? null;
