// Chain data lives in TanStack Query (queries.ts), so this store keeps only the state that the
// page owns (docs/adr/0032).
import { useSyncExternalStore } from "react";
import { config } from "../config";
import type { ParamText } from "../domain/abi";
import type { Param, Variant } from "../domain/outline";
import type { Route } from "../domain/route";
import type { ByteOffset, Source } from "../domain/source";

interface State {
  source: Source;
  // The text of each field, by `fieldKey`, kept while the program is edited.
  fields: Readonly<Record<string, string>>;
  // The last request to select a place in the editor. Each request is a new object, so that
  // the same place can be selected again.
  selection: { offset: ByteOffset } | null;
}

let state: State = { source: "" as Source, fields: {}, selection: null };
const listeners = new Set<() => void>();

function set(next: Partial<State>): void {
  state = { ...state, ...next };
  for (const l of listeners) l();
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

// Returns the part of the state that `select` picks, and renders again when it changes.
// `select` must return a stored value: a new object on each call makes React render forever.
const useSelected = <T,>(select: (s: State) => T): T =>
  useSyncExternalStore(subscribe, () => select(state));

// Returns the program in the editor.
export const useSource = (): Source => useSelected((s) => s.source);

export const useSelection = (): State["selection"] => useSelected((s) => s.selection);

// A form whose fields the store keeps: the deploy form, or the form of one `msg` variant.
export type FormId = string & { readonly __brand: "FormId" };

// The deploy form, whose fields are the parameters of `init`.
export const INIT_FORM = "init" as FormId;

// Returns the form of `variant`. It holds a dot, so it is never `INIT_FORM`.
export const formOf = (variant: Variant): FormId => `${variant.msg}.${variant.name}` as FormId;

// The key of the field `name` in `form`.
const fieldKey = (form: FormId, name: string): string => `${form}.${name}`;

// Returns each of `params` with the text of its field in `form`.
export function useFieldTexts(form: FormId, params: readonly Param[]): ParamText[] {
  const fields = useSelected((s) => s.fields);
  return params.map((param) => ({ param, text: fields[fieldKey(form, param.name)] ?? "" }));
}

const START = config.examples[config.start];
if (START === undefined) throw new Error(`config.ts has no example ${config.start}`);

// Returns the program the page opens with on `route`: the route's own, or the example
// `config.start` when it carries none.
export const initialSource = (route: Route): Source => route.source ?? START;

// Puts `source` in the editor.
export const setSource = (source: Source): void => set({ source });

// Selects the byte at `offset` in the editor, scrolls to it and focuses the editor.
export const selectInEditor = (offset: ByteOffset): void => set({ selection: { offset } });

// Sets the text of the field `name` in `form`.
export const setField = (form: FormId, name: string, text: string): void =>
  set({ fields: { ...state.fields, [fieldKey(form, name)]: text } });
