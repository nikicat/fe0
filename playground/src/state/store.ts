// Chain data lives in TanStack Query (queries.ts), so this store keeps only the state that the
// page owns (docs/adr/0032).
import { useSyncExternalStore } from "react";
import { config } from "../config";
import type { ParamText } from "../domain/abi";
import { Listeners } from "../domain/generic";
import type { Outline, Param, Variant } from "../domain/outline";
import type { Route } from "../domain/route";
import { type ByteOffset, Program, type Source } from "../domain/source";

interface State {
  program: Program;
  // The text of each field, by Form.key, kept while the program is edited.
  fields: Readonly<Record<string, string>>;
  // The last request to select a place in the editor. Each request is a new object, so that
  // the same place can be selected again.
  selection: { offset: ByteOffset } | null;
  // The text that names the deploy form's salt (domain/salt.ts).
  saltText: string;
}

// The state that the page owns.
class PageStore {
  #state: State = {
    program: new Program("" as Source), fields: {}, selection: null, saltText: "",
  };
  readonly #listeners = new Listeners();

  // Returns the part of the state that `select` picks, and renders again when it changes.
  // `select` must return a stored value: a new object on each call makes React render
  // forever.
  useSelected<T>(select: (s: State) => T): T {
    return useSyncExternalStore(this.#listeners.subscribe, () => select(this.#state));
  }

  // Puts `source` in the editor. The same source keeps its Program.
  setSource(source: Source): void {
    if (source !== this.#state.program.source) this.#set({ program: new Program(source) });
  }

  setSaltText(saltText: string): void {
    this.#set({ saltText });
  }

  // Selects the byte at `offset` in the editor, scrolls to it and focuses the editor.
  select(offset: ByteOffset): void {
    this.#set({ selection: { offset } });
  }

  // Sets the text of the field whose Form.key is `key`.
  setField(key: string, text: string): void {
    this.#set({ fields: { ...this.#state.fields, [key]: text } });
  }

  #set(next: Partial<State>): void {
    this.#state = { ...this.#state, ...next };
    this.#listeners.notify();
  }
}

export const store = new PageStore();

// Returns the program in the editor.
export const useProgram = (): Program => store.useSelected((s) => s.program);

// Returns the outline of the program in the editor.
export const useOutline = (): Outline => useProgram().outline();

export const useSelection = (): State["selection"] => store.useSelected((s) => s.selection);

export const useSaltText = (): string => store.useSelected((s) => s.saltText);

// A form whose fields the store keeps: the deploy form, or the form of one `msg` variant.
export class Form {
  // The deploy form, whose fields are the parameters of `init`.
  static readonly init = new Form("init");

  // Returns the form of `variant`. Its id holds a dot, so it is never init's.
  static of(variant: Variant): Form {
    return new Form(`${variant.msg}.${variant.name}`);
  }

  readonly id: string;

  private constructor(id: string) {
    this.id = id;
  }

  // The key of the field `name` in this form.
  key(name: string): string {
    return `${this.id}.${name}`;
  }

  // Sets the text of the field `name` in this form.
  set(name: string, text: string): void {
    store.setField(this.key(name), text);
  }
}

// Returns each of `params` with the text of its field in `form`.
export function useFieldTexts(form: Form, params: readonly Param[]): ParamText[] {
  const fields = store.useSelected((s) => s.fields);
  return params.map((param) => ({ param, text: fields[form.key(param.name)] ?? "" }));
}

const START = config.examples[config.start];
if (START === undefined) throw new Error(`config.ts has no example ${config.start}`);

// Returns the program the page opens with on `route`: the route's own, or the example
// `config.start` when it carries none.
export const initialSource = (route: Route): Source => route.source ?? START;
