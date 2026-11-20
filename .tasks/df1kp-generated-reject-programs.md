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
  - **Meaning-preserving:** re-flow whitespace and newlines, add comments, wrap
    subexpressions in parentheses or blocks, rename locals to item names or contextual words,
    insert unreachable code. Both compilers must accept the mutant. Fe0 must also give the
    original's bytes when only whitespace or comments changed.
  - **Rule-breaking, one rule per mutant:** drop the parentheses that `E.may_take_generics`
    or `E.may_read_as_record` adds, capitalize a local, name a local like a type (`u8` …
    `u256`, `i8` … `i256`), chain a comparison, make a constant cycle, drop `mut` from
    `uses`, use an effect that `uses` does not list, mismatch a type. Both must reject it.
  - **Narrowing probes:** plant the shapes of the 30 `fe: accepts` probes in random
    programs. Fe must accept them and Fe0 must reject them, with the probe's code.
- **CI:** a fixed seed range of about 200 mutants, about 4 minutes. A real bug that it finds
  gets its own probe in `corpus/reject/` (or a corpus program) and its own task.
- **Mutations work on the finished text,** not inside gen.py. So the same mutations also
  apply to `corpus/*.fe` and the reject programs, and gen.py stays as it is. A mutation finds
  its place with a tokenizer of the text. `tools/newline_check.py` has one (`TOKEN`), and it
  already re-flows generated programs inside parentheses and checks that Fe0 accepts them.
  mutate.py shares that tokenizer rather than writing a second one.
- A peer review proposed the oracle and the meaning-preserving mutations. Each of these found
  a real bug by hand (Tbb99s, Tcz2ax, T929gb, Tawfan).

## Next
- Move `TOKEN` from newline_check.py to a module that both tools import. Decide whether
  newline_check's reflow becomes a mutation of mutate.py, and keep its check of Fe's
  statement split.
- Write `tools/mutate.py` with the meaning-preserving family first, and run it on a few
  seeds.
