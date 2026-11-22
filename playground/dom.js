// The page's helpers for its elements.

export const $ = (id) => document.getElementById(id);

export const escape = (s) => s.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);

// The kinds of a status line, each a class of `.status` in style.css.
export const Status = Object.freeze({ busy: "", ok: "ok", err: "err" });

// Makes `element` a status line of the kind `kind` that shows `html`.
export function setStatus(element, kind, html) {
  element.className = `status ${kind}`;
  element.innerHTML = html;
}

// Returns a new button that shows `text`.
export function button(text) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = text;
  return b;
}
