// Shows a record's compiler by its `version()`, and does not check that the compiler is listed
// (docs/adr/0032, "Contract versions").
import type { Address } from "viem";
import { useContract } from "../state/queries";
import { HexText } from "./HexText";

export function CompilerName({ address }: { address: Address }) {
  const version = useContract(address).found?.version ?? null;
  if (version === null) return <HexText value={address} />;
  return <span className="badge" title={address}>Fe0 {version}</span>;
}
