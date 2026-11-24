// The route in the URL's fragment. Every write to the URL goes through `router`, so that
// useRoute hears of each one.
import { useSyncExternalStore } from "react";
import type { Address } from "viem";
import { Listeners } from "../domain/generic";
import { Route } from "../domain/route";
import { useDeployment } from "./deployment";

// The window's route, in its location and history.
class HashRouter {
  // history.replaceState fires no hashchange, so `replace` tells these itself.
  readonly #listeners = new Listeners();
  // The fragment that `#route` was parsed from, which may spell it in another form.
  #hash = location.hash;
  #route = Route.parse(this.#hash);

  // Adds `listener` for each change of the route, and returns the function that removes it.
  readonly subscribe = (listener: () => void): (() => void) => {
    window.addEventListener("hashchange", listener);
    const remove = this.#listeners.subscribe(listener);
    return () => {
      window.removeEventListener("hashchange", listener);
      remove();
    };
  };

  // Returns the route in the URL. It is the same object until the URL changes, as
  // useSyncExternalStore needs.
  readonly current = (): Route => {
    if (location.hash !== this.#hash) {
      this.#hash = location.hash;
      this.#route = Route.parse(this.#hash);
    }
    return this.#route;
  };

  // Opens `route`.
  navigate(route: Route): void {
    location.hash = route.hash();
  }

  // Puts `route` in the URL in place of the current one, without a new history entry.
  replace(route: Route): void {
    history.replaceState(null, "", this.url(route));
    this.#listeners.notify();
  }

  // Returns the URL of `route` on this page.
  url(route: Route): string {
    return `${location.origin}${location.pathname}${route.hash()}`;
  }
}

export const router = new HashRouter();

// Returns the route, and renders again when it changes.
export const useRoute = (): Route => useSyncExternalStore(router.subscribe, router.current);

// Links and opens the contract at an address on the page's deployment.
export type ContractLink = { href(address: Address): string; open(address: Address): void };

// Returns the ContractLink of the nearest DeploymentContext.
export function useContractLink(): ContractLink {
  const chainId = useDeployment().chain.id;
  return {
    href: (address) => Route.contract(chainId, address).hash(),
    open: (address) => router.navigate(Route.contract(chainId, address)),
  };
}
