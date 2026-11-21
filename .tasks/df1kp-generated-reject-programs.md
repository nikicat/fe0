---
status: doing
tags: [tools, subset]
---
# Generated reject programs

## Goal
`tools/gen.py` only makes programs that both compilers must accept. It avoids every shape
that Fe0 rejects (SPEC.md §1, §3.2, §3.4, §5.2), so the random rounds never test those rules.
Only the reject programs in `corpus/reject/` test them. They were written by hand, and they
check against Fe only the shapes we thought of. The generics rule shows the risk: the first
version of Fe0's rule rejected `if x < lo { lo } else if x > hi { hi }`, which Fe accepts,
and only a corpus program caught it.

Done means: `tools/mutate.py` mutates gen.py's programs and checks each mutant with the native
CLI and with `fe check`. CI runs it on a fixed range of seeds, and every finding fails the run.

## Decisions
- **An oracle, not headers.** Each mutant gets two verdicts: the native CLI's exit code (0 or
  1) and `fe check`'s. A disagreement is a finding:
  - Fe rejects and Fe0 accepts: a subset bug (ADR 0001).
  - Fe accepts and Fe0 rejects with a code that has no `fe: accepts` probe in
    `corpus/reject/`: a narrowing that SPEC.md does not state.

  It needs no `// expect:` header and no EVM run, so a mutation need not predict its code.
  Writing reject programs with headers for embed.harness is left out.
- **Cost:** `fe check` takes about 1 s per program and the native CLI about 5 ms (Fe 26.7.0).
  The tool checks one mutant at a time, because the host's memory is small.
- **Three families of mutation:**
  - **Meaning-preserving:** re-flow whitespace and newlines, add comments, wrap subexpressions in
    parentheses or blocks, rename locals to function or msg names or contextual words, insert
    unreachable code. When both compilers accept the mutant, Fe0 must give the original's bytes if
    only whitespace, comments, parentheses or a local's name changed.
  - **Rule-breaking, one rule per mutant:** drop the parentheses that `E.may_take_generics` or
    `E.may_read_as_record` adds, name a local after a type or variant in scope (`Some`), name a
    local like a primitive type (`u8` … `u256`, `i8` … `i256`), chain comparisons whose types do
    not fit, make a constant cycle, drop `mut` from `uses`, use an effect that `uses` does not
    list, mismatch a type. Fe should reject it, and Fe0 accepting it is a finding. When both
    accept it, the mutation missed its rule; the summary counts that.
  - **Narrowing probes:** plant the shapes of the `fe: accepts` probes in random
    programs. Fe must accept them and Fe0 must reject them, with the probe's code.
- **A mutant that both compilers reject is not a finding,** because it says nothing about
  the subset. The summary counts such mutants for each mutation, so that a mutation that
  mostly makes invalid programs shows up.
- **`paren` wraps only integer literals, `true`, `false` and the names the program declares.** A
  declared name is never a keyword or a type name, so the tool keeps no copy of SPEC.md §1's
  word lists, and reads no Markdown.
- **CI:** a fixed seed range of about 200 mutants, about 2.5 minutes. A real bug that it finds
  gets its own probe in `corpus/reject/` (or a corpus program) and its own task.
- **Mutations work on the finished text,** not inside gen.py. So the same mutations also
  apply to `corpus/*.fe` and the reject programs, and gen.py stays as it is. A mutation finds
  its place with one tokenizer of the text, `tools/fetokens.py`. Every tool that rewrites
  programs as text uses it, so no tool writes a second one.
- A peer review proposed the oracle and the meaning-preserving mutations. Each of these found
  a real bug by hand (Tbb99s, Tcz2ax, T929gb, Tawfan).

## State
- `tools/fetokens.py` holds the tokenizer, and `newline_check.py` imports it. `reflow` is in
  `tools/mutate.py`, and newline_check imports it from there.
- `tools/mutate.py` has six meaning-preserving mutations: `comment`, `space`, `paren` (an operand
  that is a literal or a declared name), `reflow`, `rename` (a local becomes a contextual word, a
  width with no type such as `u7`, or a lowercase function or msg name), each expected to give the
  same bytes, and `unreachable` (a `let` after a `return`), which may give other bytes. It has six
  rule-breaking ones: `type_name`, `chain`, `const_cycle`, `drop_mut`, `drop_uses` and
  `bool_for_int`. `drop_mut` misses its rule when the field is only read.
- `mutate.py -n 20 --per-program 4` checks about 250 mutants and has no findings. The rules
  that its earlier runs found each have a probe: a plain comment line before a name (SPEC.md §1),
  an uppercase local that Fe accepts (`corpus/reject/uppercase_let_not_a_type.fe`), and a
  chain of comparisons whose types fit (`corpus/chained_comparisons.fe`).

## Next
- The two rule-breaking mutations left: drop the parentheses that `E.may_take_generics` or
  `E.may_read_as_record` adds, and name a local after a type or variant in scope, such as
  `Some`.
- The narrowing probes.
- A CI step on a fixed seed range.
- `newline_check.py` tells reflowed programs apart by the `_reflowed` file-name suffix, which
  `generated()` writes and `rejected_reflows()` reads back. Give `Program` a `reflowed` flag
  (or a kind enum) that `generated()` sets, and filter on it.
- `fetokens.py` and `mutate.py` copy Fe0's lexer rules by hand: the operators of `_TOKEN`,
  `BINARY_OPS` (`Tok.is_binary`) and the assignment operators in `BEFORE_OPERAND`. Nothing
  checks the copy, so an operator added to `fe0/src/lexer.fe` silently changes the places that
  the tools pick. Add a check that compares the significant tokens of the corpus with Fe0's own
  token stream. It needs the native CLI to print its tokens, which it cannot yet.
