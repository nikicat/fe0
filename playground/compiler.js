// Compiler, the contract on chain that compiles and deploys programs.
import { decodeFunctionResult, encodeFunctionData, stringToHex } from "./viem.js";
import { $, Status, setStatus } from "./dom.js";
import { explorerLink } from "./chain.js";

// How long the editor waits after a keystroke before it compiles, in milliseconds.
const COMPILE_DELAY = 500;

// The page's side of the Compiler contract (fe0-chain/README.md).
export class Compiler {
  #data;
  #client;
  #editor;
  #showFailure;
  #timer = 0;
  // The number of the latest compile, so that an older one that answers late is ignored.
  #latest = 0;

  constructor(data, client, editor, showFailure) {
    this.#data = data;
    this.#client = client;
    this.#editor = editor;
    this.#showFailure = showFailure;
  }

  // Compiles the program in the editor on chain COMPILE_DELAY after the last call, and shows
  // the result in #status.
  compileSoon() {
    clearTimeout(this.#timer);
    this.#timer = setTimeout(() => this.#compile(), COMPILE_DELAY);
  }

  // Deploys the program in the editor through Compiler, shows the progress in `out`, and puts
  // the new contract's address in #target.
  async deploy(wallet, forms, out) {
    try {
      const args = forms.initArgs();
      const src = stringToHex(this.#editor.text);
      const tx = { to: this.#data.compiler, data: this.#calldata("deploy", [src, args]) };
      // The simulation runs on the same state as the transaction, as long as nobody else
      // deploys through Compiler in between, so it returns the address that the transaction
      // creates.
      const address = decodeFunctionResult({ abi: this.#data.abi, functionName: "deploy",
        data: await wallet.send(tx, out) });
      if (!(await this.#client.getCode({ address }))) {
        throw new Error(`The transaction created no contract at ${address}.`);
      }
      $("target").value = address;
      const link = explorerLink(this.#client.chain, `address/${address}`, address);
      out.innerHTML += ` The contract is at ${link}, and the forms below call it.`;
    } catch (e) {
      this.#showFailure(out, e);
    }
  }

  async #compile() {
    const run = ++this.#latest;
    const status = $("status");
    const src = stringToHex(this.#editor.text);
    setStatus(status, Status.busy, "Compiling on chain…");
    try {
      const tx = { to: this.#data.compiler, data: this.#calldata("compile", [src]) };
      const { data: result } = await this.#client.call(tx);
      if (run !== this.#latest) return;
      this.#editor.markLine(null);
      const code = decodeFunctionResult({ abi: this.#data.abi, functionName: "compile",
        data: result });
      const bytes = (code.length - 2) / 2;
      setStatus(status, Status.ok, `Compiled: ${bytes.toLocaleString()} bytes of deploy code.`);
      $("code").textContent = code;
      $("code-box").hidden = false;
      // As a transaction, the same compile would cost this much gas.
      this.#client.estimateGas(tx).then((gas) => {
        if (run === this.#latest) {
          status.innerHTML += ` The compile ran ${gas.toLocaleString()} gas, for free.`;
        }
      }, () => {});
    } catch (e) {
      if (run !== this.#latest) return;
      $("code-box").hidden = true;
      this.#showFailure(status, e);
    }
  }

  // Returns the calldata of Compiler's function `name` with `args`.
  #calldata(name, args) {
    return encodeFunctionData({ abi: this.#data.abi, functionName: name, args });
  }
}
