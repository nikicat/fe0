// The contracts that the registry creates through CreateX, and the addresses they get
// (docs/adr/0031-deployment-registry.md, "Deploying").
import { type Address, type Hex, concatHex, getContractAddress, keccak256 } from "viem";
import type { EncodedArgs } from "./abi";
import type { Salt } from "./salt";
import type { Program } from "./source";

// The code that deploys a compiled program, as Compiler returns it.
export type DeployCode = Hex & { readonly __brand: "DeployCode" };

// The code that CreateX runs to create a contract.
export type InitCode = Hex & { readonly __brand: "InitCode" };

// A request to the registry's `deploy`: the program, its constructor's arguments and the salt.
export class Creation {
  constructor(readonly program: Program, readonly args: EncodedArgs, readonly salt: Salt) {}

  // Returns the init code that creates this program from its deploy code `code`.
  initCode(code: DeployCode): InitCode {
    return concatHex([code, this.args]) as InitCode;
  }
}

// CreateX at `address`, which creates each contract of the registry.
export class CreateX {
  constructor(readonly address: Address) {}

  // Returns the address at which the registry creates `creation`, whose program compiles to
  // `code`.
  addressOf(creation: Creation, code: DeployCode): Address {
    return getContractAddress({
      opcode: "CREATE2", from: this.address, salt: keccak256(keccak256(creation.salt)),
      bytecode: creation.initCode(code),
    });
  }
}
