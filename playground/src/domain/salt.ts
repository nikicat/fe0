// The salts of the registry's deployments (docs/adr/0031-deployment-registry.md, "Deploying").
import { type Hex, keccak256, stringToHex, zeroHash } from "viem";

// The salt that a deployer passes to the registry's `deploy`.
export type Salt = Hex & { readonly __brand: "Salt" };

// The salt of an empty salt field.
export const NO_SALT = zeroHash as Salt;

// Returns the salt that the salt field's `text` names: NO_SALT for no text, and keccak256 of
// its UTF-8 bytes otherwise (docs/adr/0031-deployment-registry.md, "Deploying").
export const saltOf = (text: string): Salt =>
  text === "" ? NO_SALT : keccak256(stringToHex(text)) as Salt;
