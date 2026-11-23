// The typed client of Compiler (fe0-chain/README.md), from its committed interface.
import {
  type Address, type GetContractReturnType, type Hex, type PublicClient, decodeFunctionResult,
  encodeFunctionData, getContract, stringToHex,
} from "viem";
import { compilerAbi } from "../config";
import type { Deployed } from "../domain/config";
import type { Source } from "../domain/source";
import { publicClient } from "./chains";
import { codeSize } from "./contract";
import { type Progress, type Tx, transact } from "./transact";

// The code that deploys a compiled program.
export type DeployCode = Hex & { readonly __brand: "DeployCode" };

// Compiler takes a program as its UTF-8 bytes.
const programBytes = (source: Source): Hex => stringToHex(source);

// The Compiler of one deployment, which reads through the chain's RPC endpoint.
export class Compiler {
  readonly #deployment: Deployed;
  readonly #client: PublicClient;
  readonly #contract: GetContractReturnType<typeof compilerAbi, PublicClient>;

  constructor(deployment: Deployed) {
    this.#deployment = deployment;
    this.#client = publicClient(deployment);
    this.#contract = getContract({
      address: deployment.compiler, abi: compilerAbi, client: this.#client,
    });
  }

  // Returns the deploy code of `source`, from `compile` by `eth_call`. Errors with viem's
  // error when the compile fails; its revert data (./revertData.ts) holds Compiler's error,
  // such as `CompileError`.
  async compile(source: Source): Promise<DeployCode> {
    return await this.#contract.read.compile([programBytes(source)]) as DeployCode;
  }

  // Returns the gas that the compile of `source` would use as a transaction. viem estimates
  // only the gas of functions that write, and `compile` is a view.
  compileGas(source: Source): Promise<bigint> {
    return this.#client.estimateGas({
      to: this.#deployment.compiler,
      data: encodeFunctionData({
        abi: compilerAbi, functionName: "compile", args: [programBytes(source)],
      }),
    });
  }

  // Deploys `source` with the ABI-encoded `args` from the wallet, reports each step to
  // `progress`, and returns the address that the simulation gave. When another deploy through
  // Compiler lands between the simulation and the transaction, that address holds the other
  // contract, and Compiler emits no event that would tell. Errors as `transact` does, and with
  // Error when the address holds no code.
  async deploy(source: Source, args: Hex, progress: (p: Progress) => void): Promise<Address> {
    const tx: Tx = {
      to: this.#deployment.compiler,
      data: encodeFunctionData({
        abi: compilerAbi, functionName: "deploy", args: [programBytes(source), args],
      }),
    };
    const { result } = await transact(this.#deployment, tx, progress);
    const address = decodeFunctionResult({
      abi: compilerAbi, functionName: "deploy", data: result,
    });
    if (await codeSize(this.#client, address) === 0) {
      throw new Error(`The transaction created no contract at ${address}.`);
    }
    return address;
  }
}

