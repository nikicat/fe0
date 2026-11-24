// The page's routes, in the URL's fragment (docs/adr/0032, "Routes").
import { type Address, getAddress, isAddress } from "viem";
import type { ChainId } from "./config";
import type { Source } from "./source";

// The page that a route opens. Each address is checksummed (EIP-55), whatever its casing in
// the URL.
export type Place =
  // The editor.
  | { page: "editor" }
  // One contract's page.
  | { page: "contract"; chainId: ChainId; address: Address }
  // The registry's list on the default chain. `account` names the list as it does in
  // ListCursor (domain/registryList.ts).
  | { page: "registry"; account: Address | null };

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

// A place on the page and the program that its link carries, or null when it carries none.
export class Route {
  readonly place: Place;
  readonly source: Source | null;

  private constructor(place: Place, source: Source | null) {
    this.place = place;
    this.source = source;
  }

  // Returns the route of the editor, which carries `source` when it is not null.
  static editor(source: Source | null = null): Route {
    return new Route({ page: "editor" }, source);
  }

  // Returns the route of the contract at `address` on chain `chainId`. A route without a
  // program leaves the page to take its forms from the editor's program.
  static contract(chainId: ChainId, address: Address, source: Source | null = null): Route {
    return new Route({ page: "contract", chainId, address }, source);
  }

  static registry(account: Address | null = null): Route {
    return new Route({ page: "registry", account }, null);
  }

  // Returns the route of the fragment `hash`. A fragment that names no route gives the
  // editor with no program.
  static parse(hash: string): Route {
    const parts = hash.replace(/^#\/?/, "").split("/");
    const [first = "", second = "", ...rest] = parts;
    if (first === "registry" && rest.length === 0) {
      if (second === "") return Route.registry();
      if (isAddress(second)) return Route.registry(getAddress(second));
    }
    if (/^[0-9]+$/.test(first) && isAddress(second)) {
      const tail = parseTail(rest);
      const chainId = Number(first) as ChainId;
      if (tail.ok) return Route.contract(chainId, getAddress(second), tail.source);
    }
    const tail = parseTail(parts);
    return Route.editor(tail.ok ? tail.source : null);
  }

  // Returns the fragment of this route, in the form that docs/adr/0032 (Routes) gives.
  hash(): string {
    const { place } = this;
    if (place.page === "registry") {
      return place.account === null ? "#/registry" : `#/registry/${place.account}`;
    }
    const src = this.source === null ? "" : `src/${toBase64Url(this.source)}`;
    if (place.page === "editor") return `#/${src}`;
    return `#/${place.chainId}/${place.address}${src && `/${src}`}`;
  }

  // The chain that this route names, or null when it names none.
  get chainId(): ChainId | null {
    return this.place.page === "contract" ? this.place.chainId : null;
  }
}

// The fragment of the editor with no program.
export const EDITOR_HASH = Route.editor().hash();
