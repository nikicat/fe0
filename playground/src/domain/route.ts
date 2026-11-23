// The page's routes, in the URL's fragment (docs/adr/0032, "Routes").
import { type Address, isAddress } from "viem";
import type { ChainId } from "./config";
import type { Source } from "./source";

// `source` is the program that the link carries, or null when it carries none.
export type Route =
  // The editor.
  | { page: "editor"; source: Source | null }
  // One contract's page.
  | { page: "contract"; chainId: ChainId; address: Address; source: Source | null };

// Returns the UTF-8 bytes of `text` in base64url.
function toBase64Url(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_");
}

// Returns the text that `encoded` holds as UTF-8 bytes in base64url. Returns null when
// `encoded` is not base64url or its bytes are not UTF-8.
function fromBase64Url(encoded: string): string | null {
  try {
    const binary = atob(encoded.replace(/-/g, "+").replace(/_/g, "/"));
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return null;
  }
}

// Returns the fragment of `route`, in the form that docs/adr/0032 (Routes) gives.
export function routeHash(route: Route): string {
  const src = route.source === null ? "" : `src/${toBase64Url(route.source)}`;
  if (route.page === "editor") return `#/${src}`;
  return `#/${route.chainId}/${route.address}${src && `/${src}`}`;
}

// Returns the route of the contract at `address` on chain `chainId`. The route carries no
// program, so the page takes its forms from the editor's program.
export const contractRoute = (chainId: ChainId, address: Address): Route =>
  ({ page: "contract", chainId, address, source: null });

// The program that the path segments after a route's page carry, or `ok: false` when they
// name no route.
type Tail = { ok: true; source: Source | null } | { ok: false };

function parseTail(rest: string[]): Tail {
  if (rest.length === 0 || (rest.length === 1 && rest[0] === "")) {
    return { ok: true, source: null };
  }
  if (rest.length === 2 && rest[0] === "src") {
    const source = fromBase64Url(rest[1] ?? "");
    if (source !== null) return { ok: true, source: source as Source };
  }
  return { ok: false };
}

// Returns the route of the fragment `hash`. A fragment that names no route gives the editor
// with no program.
export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/");
  const [first = "", second = "", ...rest] = parts;
  if (/^[0-9]+$/.test(first) && isAddress(second)) {
    const tail = parseTail(rest);
    if (tail.ok) {
      const chainId = Number(first) as ChainId;
      return { page: "contract", chainId, address: second, source: tail.source };
    }
  }
  const tail = parseTail(parts);
  return { page: "editor", source: tail.ok ? tail.source : null };
}
