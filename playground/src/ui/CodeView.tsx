// A read-only view of a program, highlighted.
import { EditorState } from "@codemirror/state";
import { EditorView, lineNumbers } from "@codemirror/view";
import { useEffect, useRef } from "react";
import type { Source } from "../domain/source";
import { fe0Highlighting } from "./fe0Language";

export function CodeView({ source, label }: { source: Source; label: string }) {
  const parent = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const view = new EditorView({
      parent: parent.current!,
      state: EditorState.create({
        doc: source,
        extensions: [
          lineNumbers(), fe0Highlighting,
          EditorState.readOnly.of(true), EditorView.editable.of(false),
          EditorView.contentAttributes.of({ "aria-label": label }),
        ],
      }),
    });
    return () => view.destroy();
  }, [source, label]);
  return <div className="code-view" ref={parent} />;
}
