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

Some mutations preserve the program's meaning. The others each break one rule, such as ordering
a `bool` or making a constant depend on itself, so Fe should reject the mutant, and Fe0 must
reject it too.

A mutant that both compilers reject is not a finding, because it says nothing about the subset.
The summary counts these mutants for each meaning-preserving mutation, so that a mutation that
mostly makes invalid programs shows up. It also counts the rule-breaking mutants that both
compilers accept, because then the mutation missed its rule.

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

COMPARISONS: frozenset[Op] = frozenset({Op.LT, Op.GT, Op.LE, Op.GE, Op.EQ, Op.NE})
# Fe0's binary operators, as `Tok.is_binary` in fe0/src/lexer.fe names them. Inside
# parentheses, a line may end with one.
BINARY_OPS: frozenset[Op] = COMPARISONS | {
    Op.PLUS, Op.MINUS, Op.STAR, Op.SLASH, Op.PERCENT, Op.AMP, Op.PIPE, Op.CARET, Op.SHL, Op.SHR,
    Op.ANDAND, Op.OROR}
# An atom right after one of these tokens is an operand. `:` is left out, because a type
# comes after it too.
BEFORE_OPERAND: frozenset[Op | Keyword] = BINARY_OPS | {
    Op.LPAREN, Op.COMMA, Op.ASSIGN, Op.BANG, Op.TILDE, Keyword.RETURN, Op.PLUS_ASSIGN,
    Op.MINUS_ASSIGN, Op.STAR_ASSIGN, Op.SLASH_ASSIGN, Op.PERCENT_ASSIGN, Op.AMP_ASSIGN,
    Op.PIPE_ASSIGN, Op.CARET_ASSIGN, Op.SHL_ASSIGN, Op.SHR_ASSIGN}
# An operand may end right before one of these tokens. `:` is left out, because a call's label
# comes before it too.
AFTER_OPERAND: frozenset[Op] = BINARY_OPS | {Op.RPAREN, Op.COMMA, Op.RBRACE}
DECLARERS: frozenset[Keyword] = frozenset({Keyword.LET, Keyword.VAR, Keyword.CONST, Keyword.MUT})
LOCAL_DECLARERS: frozenset[Keyword] = frozenset({Keyword.LET, Keyword.VAR})
# A local may take the name of a function or a msg, which it then hides (SPEC.md §5.2). It may
# not take the name of the contract, an event or a constant (N018), or start uppercase (N017).
HIDEABLE_DECLARERS: frozenset[Keyword] = frozenset({Keyword.FN, Keyword.MSG})
BOOLS: frozenset[Keyword] = frozenset({Keyword.TRUE, Keyword.FALSE})
# Names that Fe and Fe0 both allow for a local, though they look like a keyword or a type:
# the contextual words, and integer widths that Fe has no type for (SPEC.md §1).
ODD_NAMES: tuple[FeName, ...] = tuple(map(FeName, ["init", "recv", "assert", "with", "u7", "i24"]))
# Type names. Fe and Fe0 both reject each of them as a local's name (SPEC.md §1, and §5.2 for
# `String` and `Address`, which Fe reads as a pattern).
TYPE_NAMES: tuple[FeName, ...] = tuple(map(FeName, [
    "u8", "u256", "i128", "usize", "bool", "String", "Address"]))
# No program of the corpus or of gen.py uses this name, so a local of this name hides nothing
# that a later line uses.
UNREACHABLE_LOCAL = FeName("mutant_unreachable")


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
    """What the oracle expects of a mutant, by its mutation's family (task Tdf1kp, "Three
    families of mutation")."""

    # When both compilers accept the mutant, Fe0 gives the original's bytes (task Tdf1kp).
    SAME_CODE = "same code"
    # Fe0 may give other bytes, because the mutant adds code.
    ANY_CODE = "any code"
    # Fe should reject the mutant, because it breaks one rule.
    REJECT = "reject"


class Mutation(StrEnum):
    """A meaning-preserving or a rule-breaking mutation (task Tdf1kp, "Three families of
    mutation")."""

    COMMENT = "comment"
    SPACE = "space"
    PAREN = "paren"
    REFLOW = "reflow"
    RENAME = "rename"
    UNREACHABLE = "unreachable"
    TYPE_NAME = "type_name"
    CHAIN = "chain"
    CONST_CYCLE = "const_cycle"
    DROP_MUT = "drop_mut"
    DROP_USES = "drop_uses"
    BOOL_FOR_INT = "bool_for_int"

    @property
    def expect(self) -> Expect:
        match self:
            case Mutation.UNREACHABLE:
                return Expect.ANY_CODE
            case (Mutation.COMMENT | Mutation.SPACE | Mutation.PAREN | Mutation.REFLOW
                  | Mutation.RENAME):
                return Expect.SAME_CODE
            case (Mutation.TYPE_NAME | Mutation.CHAIN | Mutation.CONST_CYCLE | Mutation.DROP_MUT
                  | Mutation.DROP_USES | Mutation.BOOL_FOR_INT):
                return Expect.REJECT

    @property
    def breaks_rule(self) -> bool:
        """True if the mutation is rule-breaking (task Tdf1kp, "Three families of mutation").
        False otherwise."""
        return self.expect == Expect.REJECT

    def mutate(self, source: FeSource, rng: random.Random) -> FeSource | None:
        """Returns a mutant of `source`, or None when `source` has no place for the mutation."""
        match self:
            case Mutation.COMMENT:
                return comment(source, rng)
            case Mutation.SPACE:
                return space(source, rng)
            case Mutation.PAREN:
                return paren(source, rng)
            case Mutation.REFLOW:
                return reflow(source, rng)
            case Mutation.RENAME:
                return rename(source, rng)
            case Mutation.UNREACHABLE:
                return unreachable(source, rng)
            case Mutation.TYPE_NAME:
                return type_name(source, rng)
            case Mutation.CHAIN:
                return chain(source, rng)
            case Mutation.CONST_CYCLE:
                return const_cycle(source, rng)
            case Mutation.DROP_MUT:
                return drop_mut(source, rng)
            case Mutation.DROP_USES:
                return drop_uses(source, rng)
            case Mutation.BOOL_FOR_INT:
                return bool_for_int(source, rng)


class Mutant(NamedTuple):
    """A program changed at one place."""

    mutation: Mutation
    source: FeSource


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


def ends_operand(t: Token) -> bool:
    """True if an operand may end right before `t`. False otherwise."""
    return t.kind == Kind.NEWLINE or t.symbol in AFTER_OPERAND


def operands(sig: list[Token], atom: Callable[[Token], bool]) -> list[Token]:
    """Returns the tokens of `sig` that `atom` accepts and that stand alone as an operand."""
    return [b for a, b, c in zip(sig, sig[1:], sig[2:])
            if atom(b) and a.symbol in BEFORE_OPERAND and ends_operand(c)]


def paren(source: FeSource, rng: random.Random) -> FeSource | None:
    """Returns `source` with parentheses around one operand that is an integer literal, `true`,
    `false` or a name the program declares (task Tdf1kp). Returns None when there is no such
    operand."""
    data = source.encode()
    sig = significant(tokens(data))
    names = declared(sig)
    atoms = operands(sig, lambda t: t.kind == Kind.NUMBER or t.symbol in BOOLS or t.word in names)
    if not atoms:
        return None
    t = rng.choice(atoms)
    return Edit(t.start, t.end, Op.LPAREN.encode() + t.text + Op.RPAREN.encode()).apply(data)


def named_after(sig: list[Token], keywords: frozenset[Keyword]) -> list[FeName]:
    """Returns the words that come right after one of `keywords`, sorted."""
    return sorted({w for a, b in zip(sig, sig[1:]) if a.symbol in keywords and (w := b.word)})


def rename_word(data: bytes, old: FeName, new: FeName) -> FeSource:
    """Returns `data` with every word `old` changed to `new`."""
    out = bytearray()
    last = 0
    for t in tokens(data):
        if t.word == old:
            out += data[last:t.start] + new.encode()
            last = t.end
    return FeSource((out + data[last:]).decode())


def rename(source: FeSource, rng: random.Random) -> FeSource | None:
    """Returns `source` with one local renamed, at every place it appears, to a name that Fe and
    Fe0 both allow for a local (task Tdf1kp, "Three families of mutation"). Returns None when the
    program has no local, or when each such name already names a local, a parameter, a constant
    or a field."""
    data = source.encode()
    sig = significant(tokens(data))
    locals_ = named_after(sig, LOCAL_DECLARERS)
    taken = declared(sig)
    hideable = [n for n in named_after(sig, HIDEABLE_DECLARERS) if n[:1].islower()]
    names = sorted(n for n in {*ODD_NAMES, *hideable} if n not in taken)
    if not locals_ or not names:
        return None
    return rename_word(data, rng.choice(locals_), rng.choice(names))


def type_name(source: FeSource, rng: random.Random) -> FeSource | None:
    """Returns `source` with one local's name, at every place it appears, changed to a type
    name. Returns None when the program has no local."""
    data = source.encode()
    locals_ = named_after(significant(tokens(data)), LOCAL_DECLARERS)
    if not locals_:
        return None
    return rename_word(data, rng.choice(locals_), rng.choice(TYPE_NAMES))


def chain(source: FeSource, rng: random.Random) -> FeSource | None:
    """Returns `source` with ` < 1` after the right operand of a comparison, so that the `bool`
    the comparison gives is ordered. Fe rejects that, because `bool` has no `Ord` (SPEC.md §3.2).
    Returns None when no comparison has an atom on its right."""
    data = source.encode()
    sig = significant(tokens(data))
    rights = [b for a, b, c in zip(sig, sig[1:], sig[2:])
              if a.symbol in COMPARISONS and b.kind in (Kind.WORD, Kind.NUMBER)
              and (ends_operand(c) or c.symbol == Op.LBRACE)]
    if not rights:
        return None
    t = rng.choice(rights)
    return Edit(t.end, t.end, b" < 1").apply(data)


def statement_end(toks: list[Token], i: int) -> Token | None:
    """Returns the line end that ends the statement holding `toks[i]`, or None when a bracket
    closes before it."""
    depth = 0
    for u in toks[i + 1:]:
        if u.kind == Kind.OPEN:
            depth += 1
        elif u.kind == Kind.CLOSE:
            depth -= 1
            if depth < 0:
                return None
        elif u.kind == Kind.NEWLINE and depth == 0:
            return u
    return None


def const_cycle(source: FeSource, rng: random.Random) -> FeSource | None:
    """Returns `source` with one constant's value replaced by the constant itself. Returns None
    when the program has no constant."""
    data = source.encode()
    toks = [t for t in tokens(data) if t.kind != Kind.COMMENT]
    edits = []
    for i, t in enumerate(toks):
        if t.symbol != Keyword.CONST:
            continue
        name = next(u for u in toks[i + 1:] if not u.kind.trivia)
        j = next(k for k in range(i + 1, len(toks)) if toks[k].symbol == Op.ASSIGN)
        if (end := statement_end(toks, j)) is not None:
            edits.append(Edit(toks[j].end, end.start, b" " + name.text))
    return rng.choice(edits).apply(data) if edits else None


class UsesClause(NamedTuple):
    """A `uses` clause, as indexes into a token list."""

    # The `uses` token.
    uses: int
    # The `)` that closes the clause's list.
    close: int


def uses_clauses(toks: list[Token]) -> list[UsesClause]:
    """Returns each `uses` clause of `toks`."""
    out = []
    for i, t in enumerate(toks):
        if t.symbol != Keyword.USES:
            continue
        depth = 0
        for k in range(i + 1, len(toks)):
            if toks[k].kind == Kind.OPEN:
                depth += 1
            elif toks[k].kind == Kind.CLOSE:
                depth -= 1
                if depth == 0:
                    out.append(UsesClause(i, k))
                    break
    return out


def drop_mut(source: FeSource, rng: random.Random) -> FeSource | None:
    """Returns `source` with one `mut` taken out of a `uses` list. Returns None when no `uses`
    list has a `mut`."""
    data = source.encode()
    toks = list(tokens(data))
    muts = [toks[k] for u in uses_clauses(toks) for k in range(u.uses, u.close)
            if toks[k].symbol == Keyword.MUT and toks[k + 1].kind == Kind.SPACE]
    if not muts:
        return None
    t = rng.choice(muts)
    return Edit(t.start, ByteOffset(t.end + 1), b"").apply(data)


def drop_uses(source: FeSource, rng: random.Random) -> FeSource | None:
    """Returns `source` with one `uses` list taken out. Returns None when it has none."""
    data = source.encode()
    toks = list(tokens(data))
    cuts = [Edit(toks[u.uses - 1 if toks[u.uses - 1].kind == Kind.SPACE else u.uses].start,
                 toks[u.close].end, b"")
            for u in uses_clauses(toks)]
    return rng.choice(cuts).apply(data) if cuts else None


def bool_for_int(source: FeSource, rng: random.Random) -> FeSource | None:
    """Returns `source` with `true` in place of one integer literal that is an operand. Returns
    None when it has none."""
    data = source.encode()
    atoms = operands(significant(tokens(data)), lambda t: t.kind == Kind.NUMBER)
    if not atoms:
        return None
    t = rng.choice(atoms)
    return Edit(t.start, t.end, Keyword.TRUE.encode()).apply(data)


def unreachable(source: FeSource, rng: random.Random) -> FeSource | None:
    """Returns `source` with a `let` statement right after a `return` statement, in the same
    block (task Tdf1kp). Returns None when no `return` ends its line in its block."""
    data = source.encode()
    toks = list(tokens(data))
    ends = [end for i, t in enumerate(toks)
            if t.symbol == Keyword.RETURN and (end := statement_end(toks, i)) is not None]
    if not ends:
        return None
    t = rng.choice(ends)
    line = f"let {UNREACHABLE_LOCAL}: u256 = 0".encode()
    return Edit(t.end, t.end, line + t.text).apply(data)


def mutants(source: FeSource, rng: random.Random, count: int) -> list[Mutant]:
    """Returns `count` mutants of `source`, or fewer when a mutation finds no place."""
    out = []
    for _ in range(count):
        mutation = rng.choice(list(Mutation))
        if (mutant := mutation.mutate(source, rng)) is not None:
            out.append(Mutant(mutation, mutant))
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
    # Both compilers accept a rule-breaking mutant, so its mutation missed the rule.
    MISSED = auto()


def finding(m: Mutant, original: Original, path: Path, known: set[DiagCode]) -> str | Agreement:
    """Checks the mutant at `path` with both compilers, and returns a line that describes the
    finding, or how the compilers agree when there is none."""
    rel = path.relative_to(ROOT)
    run = cli_check.Run.of(rel, m.source)
    fe = embed.fe_rejection(rel)
    if run.compiled():
        if fe is not None:
            return f"{rel}: Fe rejects it and Fe0 accepts it\n{fe.rstrip()}"
        if m.mutation.breaks_rule:
            return Agreement.MISSED
        if m.mutation.expect == Expect.SAME_CODE and run.program().code != original.code:
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
    agreements: Counter[tuple[Agreement, Mutation]] = Counter()
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
                case Agreement() as agreement:
                    agreements[agreement, m.mutation] += 1
    print(f"{checked} mutants: {len(findings)} findings")
    keep = [m for m in Mutation if not m.breaks_rule]
    print("both compilers reject: "
          + ", ".join(f"{m} {agreements[Agreement.BOTH_REJECT, m]}" for m in keep))
    breaks = [m for m in Mutation if m.breaks_rule]
    print("both compilers accept, so the rule was not broken: "
          + ", ".join(f"{m} {agreements[Agreement.MISSED, m]}" for m in breaks))
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
