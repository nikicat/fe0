// The deployments that config.ts records, and the one each route works on. This module builds
// no wagmi configuration, so the e2e tests import it too.
import { config } from "../config";
import type { Deployed } from "../domain/config";
import type { Route } from "../domain/route";

const [first, ...rest] = [...config.deployments].sort((a, b) => a.chain.id - b.chain.id);
if (!first) throw new Error("config.ts names no chain; deployments/ has no file");

export const deployments = [first, ...rest] as const;

// The deployment that the page uses when the route names no chain: the one with the lowest
// chain id.
export const defaultDeployment: Deployed = first;

// Returns the deployment on the chain that `route` names, or undefined when config.ts lacks
// that chain. A route that names no chain is on defaultDeployment.
export function routeDeployment(route: Route): Deployed | undefined {
  if (route.page === "editor") return defaultDeployment;
  return deployments.find((d) => d.chain.id === route.chainId);
}
