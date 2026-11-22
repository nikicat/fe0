// The failures that the page shows, and what revert data means.
import { BaseError, decodeErrorResult, isHex } from "./viem.js";
import { Status, escape, setStatus } from "./dom.js";
import { PANICS, lineCol } from "./lib.js";

// Returns the revert data that the viem error `error` carries, or null when it carries none.
// A node puts the data in its JSON-RPC error's `data`, or in `data.data`.
function revertData(error) {
  const hex = (d) => typeof d === "string" && isHex(d);
  const found = error instanceof BaseError &&
    error.walk((e) => hex(e.data) || hex(e.data?.data));
  if (!found) return null;
  return hex(found.data) ? found.data : found.data.data;
}

// Returns the text of what the revert data `hex` means, and the byte offset in the source that
// a CompileError points to. The offset is null for any other revert.
function revert(hex, data) {
  if (hex === "0x") return { offset: null, text: "Reverted with no data." };
  let decoded;
  try {
    // viem adds Solidity's Panic and Error to the ABI it is given.
    decoded = decodeErrorResult({ abi: data.abi, data: hex });
  } catch {
    return { offset: null, text: `Reverted with ${hex}.` };
  }
  switch (decoded.errorName) {
    case "CompileError": {
      const [code, offset] = decoded.args;
      const message = data.messages[code.toString()];
      const text = message ? `${message.code} ${message.text}` : `error ${code}`;
      return { offset: Number(offset), text };
    }
    case "Panic": {
      const [code] = decoded.args;
      const digits = code.toString(16).padStart(2, "0");
      const meaning = PANICS[code] ?? "unknown code";
      return { offset: null, text: `Reverted with Panic(0x${digits}): ${meaning}.` };
    }
    case "Error":
      return { offset: null, text: `Reverted with Error(${JSON.stringify(decoded.args[0])}).` };
    default:
      return { offset: null, text: `Reverted with ${hex}.` };
  }
}

// Returns `showFailure(element, error)`, which shows `error` in `element` as a failure. It
// reads revert data with the interface and messages of `data`. A compile error also marks its
// line in `editor`, and gets a link that selects where it points.
export function failures(data, editor) {
  return function showFailure(element, error) {
    const hex = revertData(error);
    if (hex === null) {
      setStatus(element, Status.err, escape(error.shortMessage ?? error.message));
      return;
    }
    const { offset, text } = revert(hex, data);
    if (offset === null) {
      setStatus(element, Status.err, escape(text));
      return;
    }
    const at = lineCol(editor.text, offset);
    editor.markLine(at.line);
    setStatus(element, Status.err,
      `<a href="#" class="at">${at.line}:${at.col}</a> ${escape(text)}`);
    element.querySelector("a.at").addEventListener("click", (e) => {
      e.preventDefault();
      editor.select(offset);
    });
  };
}
