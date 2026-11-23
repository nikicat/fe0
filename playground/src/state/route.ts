// The route in the URL's fragment. Every write to the URL goes through this module, so that
// useRoute hears of each one.
import { useSyncExternalStore } from "react";
import { type Route, parseRoute, routeHash } from "../domain/route";

// history.replaceState fires no hashchange, so replaceRoute tells these itself.
const listeners = new Set<() => void>();

const subscribe = (l: () => void) => {
  window.addEventListener("hashchange", l);
  listeners.add(l);
  return () => {
    window.removeEventListener("hashchange", l);
    listeners.delete(l);
  };
};

// Returns the route, and renders again when it changes.
export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => location.hash);
  return parseRoute(hash);
}

// Opens `route`.
export function navigate(route: Route): void {
  location.hash = routeHash(route);
}

// Puts `route` in the URL in place of the current one, without a new history entry.
export function replaceRoute(route: Route): void {
  history.replaceState(null, "", routeUrl(route));
  for (const l of listeners) l();
}

// Returns the URL of `route` on this page.
export const routeUrl = (route: Route): string =>
  `${location.origin}${location.pathname}${routeHash(route)}`;
