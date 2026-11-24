// A recorded salt, with the salt of an empty salt field shown as "none".
import { NO_SALT, type Salt } from "../domain/salt";
import { HexText } from "./HexText";

export function SaltText({ salt }: { salt: Salt }) {
  return salt === NO_SALT ? <span className="muted">none</span> : <HexText value={salt} />;
}
