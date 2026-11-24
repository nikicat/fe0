// Small generic helpers that the standard library lacks.

// Returns the least of the given values.
export const minOf = <T extends bigint>(first: T, ...rest: T[]): T =>
  rest.reduce((least, v) => v < least ? v : least, first);

// Returns the greatest of the given values.
export const maxOf = <T extends bigint>(first: T, ...rest: T[]): T =>
  rest.reduce((greatest, v) => v > greatest ? v : greatest, first);

// Returns the keys of `map` grouped by their value, in the order the values first appear.
export function groupByValue<K, V>(map: ReadonlyMap<K, V>): Map<V, K[]> {
  const groups = new Map<V, K[]>();
  for (const [key, value] of map) groups.set(value, [...groups.get(value) ?? [], key]);
  return groups;
}

// Returns `fn` computed once per argument. A call made while the first one runs shares its
// promise, and a rejected call is forgotten, so the next call for its argument tries again.
export function memoize<A, R>(fn: (arg: A) => Promise<R>): (arg: A) => Promise<R> {
  const results = new Map<A, Promise<R>>();
  return (arg) => {
    let result = results.get(arg);
    if (result === undefined) {
      result = fn(arg);
      results.set(arg, result);
      result.catch(() => results.delete(arg));
    }
    return result;
  };
}

// Functions to call on each change of something they watch.
export class Listeners {
  readonly #listeners = new Set<() => void>();

  // Adds `listener`, and returns the function that removes it.
  readonly subscribe = (listener: () => void): (() => void) => {
    this.#listeners.add(listener);
    return () => { this.#listeners.delete(listener); };
  };

  // Calls each listener.
  notify(): void {
    for (const l of this.#listeners) l();
  }
}

// Returns `fn` computed once per argument.
export function memoizeSync<A, R>(fn: (arg: A) => R): (arg: A) => R {
  const results = new Map<A, R>();
  return (arg) => {
    if (!results.has(arg)) results.set(arg, fn(arg));
    return results.get(arg)!;
  };
}
