// The forms that the page draws from the program (playground/README.md, "Design").
import { decodeAbiParameters, encodeAbiParameters } from "./viem.js";
import { $, Status, button, escape, setStatus } from "./dom.js";
import { isAddress, outline, parseValue, placeholder } from "./lib.js";

// Fills `container` with an input for each of `fields`, and returns each input with its field.
function fieldInputs(container, fields) {
  container.replaceChildren();
  return fields.map((f) => {
    const row = document.createElement("label");
    row.className = "field";
    const name = document.createElement("span");
    name.textContent = `${f.name}: ${f.type}`;
    const input = document.createElement("input");
    input.placeholder = placeholder(f.abi);
    input.spellcheck = false;
    row.append(name, input);
    container.append(row);
    return { field: f, input };
  });
}

// Returns the ABI encoding of the values that `inputs` hold. Errors with Error when a field's
// type has no ABI type, or when an input does not hold a value of its type.
function encodeInputs(inputs) {
  for (const { field } of inputs) {
    if (!field.abi) {
      throw new Error(`${field.name} has the type ${field.type}, which has no ABI type`);
    }
  }
  return encodeAbiParameters(inputs.map(({ field }) => ({ type: field.abi })),
    inputs.map(({ field, input }) => {
      try {
        return parseValue(field.abi, input.value);
      } catch (e) {
        throw new Error(`${field.name}: ${e.message}`);
      }
    }));
}

// Returns the address in the field #target. Errors with Error when it holds no address.
function target() {
  const address = $("target").value.trim();
  if (!isAddress(address)) throw new Error("Enter the address of a deployed contract above.");
  return address;
}

// Returns the text that shows `result`, the return data of a variant whose return type is
// `returns`.
function describeReturn(returns, result) {
  if (!returns) return "Returned.";
  if (!returns.abi) return `Returned ${result}`;
  const [value] = decodeAbiParameters([{ type: returns.abi }], result);
  return `Returned ${value}`;
}

// The form of the program's `init`, and a form for each variant of its `msg` types. A call
// goes to the public client `client`, and a send to `wallet`.
export class Forms {
  #client;
  #wallet;
  #showFailure;
  // The form values, by form and field, kept while the program is edited.
  #kept = new Map();
  // The outline that the forms were last drawn from, so that edits elsewhere keep the forms.
  #drawn = "";
  #initInputs = [];

  constructor({ client, wallet, showFailure }) {
    this.#client = client;
    this.#wallet = wallet;
    this.#showFailure = showFailure;
  }

  // Returns the ABI encoding of the arguments of `init` in its form. Errors as `encodeInputs`
  // does.
  initArgs() {
    return encodeInputs(this.#initInputs);
  }

  // Draws the forms of the program `text`, unless they were last drawn from the same outline.
  draw(text) {
    const o = outline(text);
    const key = JSON.stringify(o);
    if (key === this.#drawn) return;
    this.#drawn = key;
    this.#initInputs = fieldInputs($("init-args"), o.init);
    this.#keep("init", this.#initInputs);
    const list = $("variants");
    list.replaceChildren();
    for (const v of o.variants) list.append(this.#variantForm(v));
    if (o.variants.length === 0) {
      list.innerHTML = `<p class="hint">The program has no <code>msg</code> variants.</p>`;
    }
  }

  // Makes `inputs`, the inputs of the form `key`, keep their values across redraws.
  #keep(key, inputs) {
    for (const { field, input } of inputs) {
      const k = `${key}.${field.name}`;
      if (this.#kept.has(k)) input.value = this.#kept.get(k);
      input.addEventListener("input", () => this.#kept.set(k, input.value));
    }
  }

  #variantForm(v) {
    const box = document.createElement("div");
    box.className = "variant";
    const title = document.createElement("h3");
    title.innerHTML = `${escape(v.name)} <small>${v.selector ?? "no selector"}` +
      `${v.returns ? ` → ${escape(v.returns.type)}` : ""}</small>`;
    const fields = document.createElement("div");
    fields.className = "fields";
    const inputs = fieldInputs(fields, v.fields);
    this.#keep(`${v.msg}.${v.name}`, inputs);
    const callButton = button("Call");
    const sendButton = button("Send");
    const row = document.createElement("div");
    row.className = "row";
    row.append(callButton, sendButton);
    const out = document.createElement("p");
    out.className = "status";
    box.append(title, fields, row, out);

    // Returns the transaction of the variant to the address in #target, from its form.
    // Errors with Error as `target` and `encodeInputs` do, or when the variant has no
    // selector.
    function tx() {
      const to = target();
      if (v.selector === null) {
        throw new Error("The variant's selector is not a 4-byte integer.");
      }
      return { to, data: v.selector + encodeInputs(inputs).slice(2) };
    }

    callButton.addEventListener("click", async () => {
      try {
        const { data: result = "0x" } = await this.#client.call(tx());
        setStatus(out, Status.ok, escape(describeReturn(v.returns, result)));
      } catch (e) {
        this.#showFailure(out, e);
      }
    });
    sendButton.addEventListener("click", async () => {
      try {
        await this.#wallet.send(tx(), out);
      } catch (e) {
        this.#showFailure(out, e);
      }
    });
    return box;
  }
}
