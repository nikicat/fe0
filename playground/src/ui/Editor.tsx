// The program editor, CodeMirror 6 with the compile error marked in place (ADR 0032).
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { bracketMatching, indentUnit, syntaxHighlighting } from "@codemirror/language";
import { type Diagnostic, setDiagnostics } from "@codemirror/lint";
import { EditorState, type Extension } from "@codemirror/state";
import { EditorView, highlightActiveLine, keymap, lineNumbers } from "@codemirror/view";
import { useEffect, useRef } from "react";
import { describeRevert } from "../domain/revert";
import { type ByteOffset, type Source, charRange } from "../domain/source";
import type { CompileView } from "../state/queries";
import { setSource, useSelection, useSource } from "../state/store";
import { fe0, fe0Highlight } from "./fe0Language";

const INDENT = 4;

// The program that `state` holds. The editor is where an edited program enters the page.
const sourceOf = (state: EditorState): Source => state.doc.toString() as Source;

export interface Mark {
  offset: ByteOffset;
  text: string;
}

// Returns the mark of the compile error that `view` failed with, if any.
export function compileMark(view: CompileView): Mark | null {
  if (view.kind !== "failed" || view.failure.kind !== "compile") return null;
  const { revert } = view.failure;
  return { offset: revert.offset, text: describeRevert(revert) };
}

// Returns the editor's extensions, which pass each edited source to `onChange`.
function editorExtensions(onChange: (source: Source) => void): Extension[] {
  return [
    lineNumbers(), history(), bracketMatching(), highlightActiveLine(),
    indentUnit.of(" ".repeat(INDENT)), EditorState.tabSize.of(INDENT),
    keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
    fe0, syntaxHighlighting(fe0Highlight),
    EditorView.contentAttributes.of({ "aria-label": "Fe0 source" }),
    EditorView.updateListener.of((u) => {
      if (u.docChanged) onChange(sourceOf(u.state));
    }),
  ];
}

export function Editor({ mark }: { mark: Mark | null }) {
  const parent = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const source = useSource();
  const selection = useSelection();

  useEffect(() => {
    const v = new EditorView({
      parent: parent.current!,
      state: EditorState.create({ doc: source, extensions: editorExtensions(setSource) }),
    });
    view.current = v;
    return () => {
      view.current = null;
      v.destroy();
    };
    // The view is made once; later sources come in through the next effect.
  }, []);

  // A source from outside the editor, such as an example or a link, replaces the document.
  useEffect(() => {
    const v = view.current;
    if (v && sourceOf(v.state) !== source) {
      v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: source } });
    }
  }, [source]);

  useEffect(() => {
    const v = view.current;
    if (!v || !selection) return;
    const { from, to } = charRange(sourceOf(v.state), selection.offset);
    v.dispatch({ selection: { anchor: from, head: to }, scrollIntoView: true });
    v.focus();
  }, [selection]);

  useEffect(() => {
    const v = view.current;
    if (!v) return;
    const diagnostics: Diagnostic[] = [];
    if (mark) {
      diagnostics.push({ ...charRange(sourceOf(v.state), mark.offset), severity: "error",
        message: mark.text });
    }
    v.dispatch(setDiagnostics(v.state, diagnostics));
  }, [mark, source]);

  return <div className="editor" ref={parent} />;
}
