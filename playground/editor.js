// The editor of the program, and its share link.
import { charIndex, lineCol, lineCount, linkFragment } from "./lib.js";

// A textarea for the program, with a gutter of line numbers that marks the line of the last
// compile error.
export class Editor {
  #source;
  #gutter;
  #edited;
  // The line that the last compile error points to, or null when there is none.
  #badLine = null;

  // Makes an editor of the textarea `source` and the gutter `gutter`. It calls `edited` after
  // each edit.
  constructor(source, gutter, edited) {
    this.#source = source;
    this.#gutter = gutter;
    this.#edited = edited;
    source.addEventListener("input", () => this.#changed());
    source.addEventListener("scroll", () => { gutter.scrollTop = source.scrollTop; });
    source.addEventListener("keydown", (e) => {
      if (e.key !== "Tab" || e.shiftKey) return;
      e.preventDefault();
      source.setRangeText("    ", source.selectionStart, source.selectionEnd, "end");
      this.#changed();
    });
  }

  get text() {
    return this.#source.value;
  }

  // Replaces the program with `text`, as an edit.
  open(text) {
    this.#source.value = text;
    this.#source.scrollTop = 0;
    this.#changed();
  }

  // Marks `line` in the gutter as the line of the last compile error, or no line for null.
  markLine(line) {
    this.#badLine = line;
    this.#drawGutter();
  }

  // Selects the byte at `offset` and scrolls to it.
  select(offset) {
    const source = this.#source;
    const index = charIndex(source.value, offset);
    source.focus();
    source.setSelectionRange(index, index + 1);
    const { line } = lineCol(source.value, offset);
    const lineHeight = parseFloat(getComputedStyle(source).lineHeight);
    source.scrollTop = Math.max(0, (line - 5) * lineHeight);
  }

  #changed() {
    this.#drawGutter();
    this.#edited();
  }

  #drawGutter() {
    this.#gutter.innerHTML = Array.from({ length: lineCount(this.text) }, (_, i) =>
      i + 1 === this.#badLine ? `<span class="bad">${i + 1}</span>` : `${i + 1}`).join("\n");
    this.#gutter.scrollTop = this.#source.scrollTop;
  }
}

// Makes `button` put a share link of the program in `editor` in the address bar and copy it.
export function shareButton(button, editor) {
  const label = button.textContent;
  button.addEventListener("click", async () => {
    const url = `${location.origin}${location.pathname}${linkFragment(editor.text)}`;
    history.replaceState(null, "", url);
    try {
      await navigator.clipboard.writeText(url);
      button.textContent = "Link copied";
    } catch {
      button.textContent = "Link in the address bar";
    }
    setTimeout(() => { button.textContent = label; }, 2000);
  });
}
