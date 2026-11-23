// The deployment that the page's panels work on, which they take from a context, not a prop
// (docs/adr/0032, "Deployment").
import { createContext, useContext } from "react";
import type { Deployed } from "../domain/config";

export const DeploymentContext = createContext<Deployed | null>(null);

// Returns the deployment of the nearest DeploymentContext. Errors with Error when a component
// renders outside one.
export function useDeployment(): Deployed {
  const deployed = useContext(DeploymentContext);
  if (!deployed) throw new Error("useDeployment ran outside a DeploymentContext.");
  return deployed;
}
