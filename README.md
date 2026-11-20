# Fe0

Fe0 is a small subset of [Fe](https://github.com/argotorg/fe) for writing EVM contracts, with a
compiler written in Fe. [docs/SPEC.md](docs/SPEC.md) defines the language, and
[docs/DESIGN.md](docs/DESIGN.md) describes the compiler.

## Fe0 as a subset to formalize

The Fe team wants a subset of Fe small enough to formalize in Lean. Fe0 could be that subset.
Nothing here is formalized yet. This section says what a model could start from.

By the [subset rule](docs/SPEC.md), Fe accepts every Fe0 program and runs it the same way. So a
theorem about Fe0's programs is a theorem about those Fe programs.

**What keeps a model small.**
- One grammar (SPEC §3.1), three value types (SPEC §2), and no generics, traits, references or
  memory.
- A name in a body means the innermost declaration of that name (SPEC §5.2). No constant
  depends on itself (SPEC §5.3).
- SPEC §4 fixes the order of every operand, argument, field value and assignment. So the
  semantics is a function: a state and a call give one outcome.
- An outcome is success with return data, or failure with revert data, plus the storage writes
  and logs of a success. SPEC §4 and §6 give the revert data of each failure.
- The model takes as inputs the values of the `Ctx` methods (SPEC §6) and what each external
  call returns. It may treat `keccak256`, which places map entries and names events, as an
  injective function.
- The subset rule leaves out gas and Fe's recursion limit. So the model needs neither.

**What a model could prove.**
- Type safety: a body that the checker accepts gives a value of its type, or fails with the
  revert data of SPEC §4 and §6.
- Effect safety, the point of Fe0 (SPEC §6): a body reads, emits and calls only through the
  entries that its `uses` lists, and writes only through the fields that it lists `mut`.
- Free functions are pure (SPEC §5.5): their result depends only on their arguments.
- The dispatcher and `init` decode their input as SPEC §6 says.
- Fe0's output, or Fe's, runs as the model says. The differential tests of SPEC §8 check this
  on each program of the corpus.

**What is hard to model.** The concrete syntax. The newline rule of SPEC §3.4 and the rule for
`<` in SPEC §3.2 exist to match Fe's parser. A model can start from the syntax tree, as the
grammar of SPEC §3.1 gives it, and leave the parser to the tests.
