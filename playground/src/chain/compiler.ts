// The typed client of Compiler (fe0-chain/README.md), from its committed interface.
import {
  type GetContractReturnType, type PublicClient, encodeFunctionData, getContract,
} from "viem";
import { compilerAbi } from "../config";
import type { Deployed } from "../domain/config";
import type { DeployCode } from "../domain/createx";
import type { Program } from "../domain/source";
import { publicClient } from "./chains";

// The Compiler of one deployment, which reads through the chain's RPC endpoint.
export class Compiler {
  readonly #client: PublicClient;
  readonly #contract: GetContractReturnType<typeof compilerAbi, PublicClient>;

  constructor(deployment: Deployed) {
    this.#client = publicClient(deployment);
    this.#contract = getContract({
      address: deployment.compiler.address, abi: compilerAbi, client: this.#client,
    });
  }

  // Returns the deploy code of `program`, from `compile` by `eth_call`. Errors with viem's
  // error when the compile fails; its revert data (./revertData.ts) holds Compiler's error,
  // such as `CompileError`.
  async compile(program: Program): Promise<DeployCode> {
    return await this.#contract.read.compile([program.bytes()]) as DeployCode;
  }

  // Returns the gas that the compile of `program` would use as a transaction. viem estimates
  // only the gas of functions that write, and `compile` is a view.
  compileGas(program: Program): Promise<bigint> {
    return this.#client.estimateGas({
      to: this.#contract.address,
      data: encodeFunctionData({
        abi: compilerAbi, functionName: "compile", args: [program.bytes()],
      }),
    });
  }
}

