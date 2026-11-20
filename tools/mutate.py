#!/usr/bin/env python3
"""Mutate accepted programs and check each mutant against Fe (task Tdf1kp).

Each mutant changes an accepted program at one place. The native CLI (fe0-cli) and the
official compiler's `fe check` each accept or reject it. Fe0 is a strict subset of Fe
(ADR 0001), so a finding is:

- a mutant that Fe rejects and Fe0 accepts;
- a mutant that Fe accepts and Fe0 rejects with a code that no `// fe: accepts` program of
  corpus/reject/ has. SPEC.md states no such narrowing;
- a mutant that should keep the program's code, such as one with an added comment, and that Fe0
  compiles to other bytes.

A mutant that both compilers reject is not a finding, because it says nothing about the subset.
The summary counts these mutants for each mutation, so that a mutation that mostly makes invalid
programs shows up.

The programs are corpus/*.fe and the generated programs of the seeds. The same seed always
gives the same mutants. Each mutant is written to out/mutate/, so a finding can be read there.

usage: mutate.py [--seed N] [-n N] [--per-program N]
"""
import argparse
import random
import sys
from collections import Counter
from collections.abc import Callable
from enum import Enum, StrEnum, auto
from pathlib import Path
from typing import NamedTuple

import cli_check
import embed
from fegen import ROOT, ByteOffset, DiagCode, FeName, FeSource
from fetokens import Keyword, Kind, Op, Token, significant, tokens
from gen import GEN, Gen

OUT: Path = ROOT / "out/mutate"

# Fe0's binary operators, as `Tok.is_binary` in fe0/src/lexer.fe names them. Inside
# parentheses, a line may end with one.
BINARY_OPS: frozenset[Op] = frozenset({
    Op.PLUS, Op.MINUS, Op.STAR, Op.SLASH, Op.PERCENT, Op.AMP, Op.PIPE, Op.CARET, Op.SHL, Op.SHR,
    Op.LT, Op.GT, Op.LE, Op.GE, Op.EQ, Op.NE, Op.ANDAND, Op.OROR})
# An atom right after one of these tokens is an operand. `:` is left out, because a type
# comes after it too.
BEFORE_OPERAND: frozenset[Op | Keyword] = BINARY_OPS | {
    Op.LPAREN, Op.COMMA, Op.ASSIGN, Op.BANG, Op.TILDE, Keyword.RETURN, Op.PLUS_ASSIGN,
    Op.MINUS_ASSIGN, Op.STAR_ASSIGN, Op.SLASH_ASSIGN, Op.PERCENT_ASSIGN, Op.AMP_ASSIGN,
    Op.PIPE_ASSIGN, Op.CARET_ASSIGN, Op.SHL_ASSIGN, Op.SHR_ASSIGN}
# An operand may end right before one of these tokens, or before a line end. `:` is left out,
# because a call's label comes before it too.
AFTER_OPERAND: frozenset[Op] = BINARY_OPS | {Op.RPAREN, Op.COMMA, Op.RBRACE}
DECLARERS: frozenset[Keyword] = frozenset({Keyword.LET, Keyword.VAR, Keyword.CONST, Keyword.MUT})
BOOLS: frozenset[Keyword] = frozenset({Keyword.TRUE, Keyword.FALSE})


def reflow(source: FeSource, rng: random.Random) -> FeSource:
    """Returns `source` with a line break in about half of the places inside parentheses where
    Fe0 allows one: after a `(`, a `,` or a binary operator, and before a `)`."""
    data = source.encode()
    out = bytearray()
    # The open brackets.
    stack: list[Token] = []
    last = ByteOffset(0)
    prev: Token | None = None

    def maybe_break(at: ByteOffset, replace: int) -> None:
        """Puts a line break at `at` in place of `replace` bytes, half of the time."""
        nonlocal last
        if stack and stack[-1].symbol == Op.LPAREN and rng.random() < 0.5:
            out.extend(data[last:at] + b"\n")
            last = ByteOffset(at + replace)

    for t in tokens(data):
        match t.kind:
            case Kind.OPEN:
                stack.append(t)
                maybe_break(t.end, 0)
            case Kind.CLOSE:
                maybe_break(t.start, 0)
                stack.pop()
            case Kind.SPACE if prev is not None and (prev.symbol == Op.COMMA
                                                     or prev.symbol in BINARY_OPS):
                maybe_break(t.start, t.end - t.start)
        if not t.kind.trivia:
            prev = t
    out.extend(data[last:])
    return FeSource(out.decode())


class Expect(Enum):
    """What a mutation keeps of the program it mutates."""

    # When both compilers accept the mutant, Fe0 gives the original's bytes (task Tdf1kp).
    SAME_CODE = "same code"


class Mutation(StrEnum):
    """A meaning-preserving mutation (task Tdf1kp, "Three families of mutation")."""

    COMMENT = "comment"
    SPACE = "space"
    PAREN = "paren"
    REFLOW = "reflow"


class Mutant(NamedTuple):
    """A program changed at one place."""

    mutation: Mutation
    source: FeSource
    expect: Expect


class Edit(NamedTuple):
    """Bytes that replace `data[start:end]`."""

    start: ByteOffset
    end: ByteOffset
    text: bytes

    def apply(self, data: bytes) -> FeSource:
        return FeSource((data[:self.start] + self.text + data[self.end:]).decode())


def comment(source: FeSource, rng: random.Random) -> FeSource | None:
    """Returns `source` with a plain comment at the end of a line, or with a plain comment line
    after it. Returns None when `source` has no line end."""
    data = source.encode()
    ends = [t for t in tokens(data) if t.kind == Kind.NEWLINE]
    if not ends:
        return None
    t = rng.choice(ends)
    edit = Edit(t.start, t.start, b" // mutant") if rng.random() < 0.5 else \
        Edit(t.end, t.end, b"// mutant" + t.text)
    return edit.apply(data)


def space(source: FeSource, rng: random.Random) -> FeSource | None:
    """Returns `source` with a space between two adjacent tokens on one line. Returns None when no
    two tokens touch."""
    data = source.encode()
    toks = list(tokens(data))
    joints = [b.start for a, b in zip(toks, toks[1:])
              if not a.kind.trivia and a.kind != Kind.NEWLINE
              and b.kind not in (Kind.SPACE, Kind.NEWLINE)]
    if not joints:
        return None
    at = rng.choice(joints)
    return Edit(at, at, b" ").apply(data)


def declared(sig: list[Token]) -> set[FeName]:
    """Returns the names that a program declares: each word after `let`, `var`, `const` or `mut`,
    and each word before a parameter's `:`."""
    names: set[FeName] = set()
    next_paren_opens_params = False
    opens_params: list[bool] = []
    for i, t in enumerate(sig):
        before = sig[i - 1].symbol if i > 0 else None
        after = sig[i + 1].symbol if i + 1 < len(sig) else None
        if t.kind == Kind.OPEN:
            opens_params.append(t.symbol == Op.LPAREN and next_paren_opens_params)
            next_paren_opens_params = False
        elif t.kind == Kind.CLOSE:
            if opens_params:
                opens_params.pop()
        elif (word := t.word) is None:
            continue
        elif t.symbol == Keyword.FN or (t.symbol == Keyword.INIT and after == Op.LPAREN):
            next_paren_opens_params = True
        elif before in DECLARERS and t.symbol != Keyword.MUT:
            # A `mut` after a `:` makes a type mutable, as in `log: mut Log`.
            if not (before == Keyword.MUT and i > 1 and sig[i - 2].symbol == Op.COLON):
                names.add(word)
        elif after == Op.COLON and opens_params and opens_params[-1]:
            names.add(word)
    return names


def paren(source: FeSource, rng: random.Random) -> FeSource | None:
    """Returns `source` with parentheses around one operand that is an integer literal, `true`,
    `false` or a name the program declares (task Tdf1kp). Returns None when there is no such
    operand."""
    data = source.encode()
    sig = significant(tokens(data))
    names = declared(sig)
    atoms = [b for a, b, c in zip(sig, sig[1:], sig[2:])
             if (b.kind == Kind.NUMBER or b.symbol in BOOLS or b.word in names)
             and a.symbol in BEFORE_OPERAND
             and (c.kind == Kind.NEWLINE or c.symbol in AFTER_OPERAND)]
    if not atoms:
        return None
    t = rng.choice(atoms)
    return Edit(t.start, t.end, Op.LPAREN.encode() + t.text + Op.RPAREN.encode()).apply(data)


# Returns a mutant of the source, or None when the source has no place for the mutation.
MutationFn = Callable[[FeSource, random.Random], FeSource | None]
MUTATIONS: dict[Mutation, MutationFn] = {Mutation.COMMENT: comment, Mutation.SPACE: space,
                                         Mutation.PAREN: paren, Mutation.REFLOW: reflow}


def mutants(source: FeSource, rng: random.Random, count: int) -> list[Mutant]:
    """Returns `count` mutants of `source`, or fewer when a mutation finds no place."""
    out = []
    for _ in range(count):
        mutation = rng.choice(list(Mutation))
        if (mutant := MUTATIONS[mutation](source, rng)) is not None:
            out.append(Mutant(mutation, mutant, Expect.SAME_CODE))
    return out


def known_narrowings() -> set[DiagCode]:
    """Returns the codes of the reject programs that Fe accepts, which SPEC.md states as
    narrowings of Fe's rules."""
    rejects = map(embed.Reject.load, sorted(embed.REJECTS.glob("*.fe")))
    return {r.expected.code for r in rejects if r.fe_accepts}


class Original(NamedTuple):
    """An accepted program, and the bytes that Fe0 compiles it to."""

    path: Path
    source: FeSource
    code: bytes


class Agreement(Enum):
    ACCEPTED = auto()
    BOTH_REJECT = auto()
    KNOWN_NARROWING = auto()


def finding(m: Mutant, original: Original, path: Path, known: set[DiagCode]) -> str | Agreement:
    """Checks the mutant at `path` with both compilers, and returns a line that describes the
    finding, or how the compilers agree when there is none."""
    rel = path.relative_to(ROOT)
    run = cli_check.Run.of(rel, m.source)
    fe = embed.fe_rejection(rel)
    if run.compiled():
        if fe is not None:
            return f"{rel}: Fe rejects it and Fe0 accepts it\n{fe.rstrip()}"
        if m.expect == Expect.SAME_CODE and run.program().code != original.code:
            return f"{rel}: Fe0 compiles it to other bytes than {original.path}"
        return Agreement.ACCEPTED
    if fe is not None:
        return Agreement.BOTH_REJECT
    error = run.error()
    if error is None:
        return f"{rel}: Fe0 does not compile it cleanly: {run.said()}"
    if error.code in known:
        return Agreement.KNOWN_NARROWING
    return f"{rel}: Fe accepts it and Fe0 rejects it: {error.describe(m.source)}"


def originals(seed: int, n: int) -> list[Original]:
    """Returns the corpus programs and the generated programs of seeds `seed` to `seed + n - 1`,
    each with Fe0's bytes. Errors with RuntimeError when Fe0 does not compile one."""
    named = [(p, FeSource(p.read_text())) for p in sorted(embed.CORPUS.glob("*.fe"))]
    named += [(GEN / f"s{s}.fe", FeSource(Gen(s).program().program)) for s in range(seed, seed + n)]
    out = []
    for path, source in named:
        run = cli_check.Run.of(path.relative_to(ROOT), source)
        if not run.compiled():
            raise RuntimeError(f"Fe0 does not compile {run.path}: {run.said()}")
        out.append(Original(run.path, source, run.program().code))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=1, help="the first seed (default 1)")
    ap.add_argument("-n", type=int, default=10, help="the number of generated programs (default 10)")
    ap.add_argument("--per-program", type=int, default=2,
                    help="the number of mutants of each program (default 2)")
    args = ap.parse_args()
    cli_check.build()
    known = known_narrowings()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.fe"):
        old.unlink()
    findings = []
    both_reject: Counter[Mutation] = Counter()
    checked = 0
    for original in originals(args.seed, args.n):
        rng = random.Random(f"{args.seed}:{original.path.stem}")
        for i, m in enumerate(mutants(original.source, rng, args.per_program)):
            path = OUT / f"{original.path.stem}_{m.mutation}_{i}.fe"
            path.write_text(m.source)
            checked += 1
            match finding(m, original, path, known):
                case str() as line:
                    print(line, flush=True)
                    findings.append(line)
                case Agreement.BOTH_REJECT:
                    both_reject[m.mutation] += 1
    print(f"{checked} mutants: {len(findings)} findings")
    print("both compilers reject: " + ", ".join(f"{m} {both_reject[m]}" for m in Mutation))
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
