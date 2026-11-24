// What the deploy form shows before deploying (docs/adr/0031-deployment-registry.md,
// "Deploying").
import type { Address } from "viem";
import { createx } from "../chain/registry";
import { type ArgsResult, type ParamText, tryEncodeArgs } from "../domain/abi";
import { Creation, type DeployCode } from "../domain/createx";
import { saltOf } from "../domain/salt";
import type { Program } from "../domain/source";
import { useContract } from "./queries";
import { Form, useFieldTexts, useSaltText } from "./store";

export interface DeployPreview {
  texts: ParamText[];
  saltText: string;
  encoded: ArgsResult;
  // What a deploy would send, or null until the arguments encode.
  creation: Creation | null;
  // Where the registry creates the contract, or null until the program compiles and its
  // arguments encode.
  address: Address | null;
  // The address when a contract is already there, or null.
  existing: Address | null;
  // The constructor call, such as `Counter(2)`, or null when it cannot be written.
  call: string | null;
}

// Returns what the deploy form shows before deploying `program`, from the arguments and the
// salt in the store. The address is null while `code` is null.
export function useDeployPreview(program: Program, code: DeployCode | null): DeployPreview {
  const outline = program.outline();
  const texts = useFieldTexts(Form.init, outline.init);
  const saltText = useSaltText();
  const encoded = tryEncodeArgs(texts);
  const creation = "args" in encoded
    ? new Creation(program, encoded.args, saltOf(saltText)) : null;
  const address = code !== null && creation !== null ? createx.addressOf(creation, code) : null;
  const existing = useContract(address).found === null ? null : address;
  const call = creation === null ? null : outline.constructorCall(creation.args);
  return { texts, saltText, encoded, creation, address, existing, call };
}
