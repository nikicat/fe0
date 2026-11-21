#!/usr/bin/env python3
"""Mutate accepted programs and check each mutant with Fe0's native CLI and with `fe check`.

The programs are corpus/*.fe and the generated programs of the seeds. The same seed always gives
the same mutants. Each mutant is written to out/mutate/, so a finding can be read there. The
tool prints each finding and a summary, and exits with 1 when it finds one. Task Tdf1kp
(.tasks/df1kp-generated-reject-programs.md) says what counts as a finding and which mutations
there are.

usage: mutate.py [--seed N] [-n N] [--per-program N]
"""
import argparse
import random
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from enum import Enum, StrEnum, auto
from pathlib import Path
from typing import NamedTuple

import cli_check
import embed
from fegen import ROOT, ByteOffset, DiagCode, FeName, FeSource
from fetokens import (ASSIGN_OPS, BracketPair, Brackets, Keyword, Kind, Op, Token, TokenIndex,
                      next_index, significant, tokens)
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
BEFORE_OPERAND: frozenset[Op | Keyword] = BINARY_OPS | ASSIGN_OPS | {
    Op.LPAREN, Op.COMMA, Op.BANG, Op.TILDE, Keyword.RETURN}
# An operand may end right before one of these tokens. `:` is left out, because a call's label
# comes before it too.
AFTER_OPERAND: frozenset[Op] = BINARY_OPS | {Op.RPAREN, Op.COMMA, Op.RBRACE}
DECLARERS: frozenset[Keyword] = frozenset({Keyword.LET, Keyword.VAR, Keyword.CONST, Keyword.MUT})
LOCAL_DECLARERS: frozenset[Keyword] = frozenset({Keyword.LET, Keyword.VAR})
# A local may take the name of a function or a msg, which it then hides, unless the name starts
# uppercase (N017, SPEC.md §5.2). For the item names that a local may not take, see
# PATTERN_DECLARERS.
HIDEABLE_DECLARERS: frozenset[Keyword] = frozenset({Keyword.FN, Keyword.MSG})
BOOLS: frozenset[Keyword] = frozenset({Keyword.TRUE, Keyword.FALSE})
# Names that Fe and Fe0 both allow for a local, though they look like a keyword or a type:
# the contextual words, and integer widths that Fe has no type for (SPEC.md §1).
ODD_NAMES: tuple[FeName, ...] = tuple(map(FeName, ["init", "recv", "assert", "with", "u7", "i24"]))
# Type names, which Fe0 rejects as a local's name. Fe's narrower rule is in SPEC.md §1, and in
# §5.2 for `String` and `Address`.
TYPE_NAMES: tuple[FeName, ...] = tuple(map(FeName, [
    "u8", "u256", "i128", "usize", "bool", "String", "Address"]))
# A `(` right after one of these tokens, or at the start of a line, opens the whole left operand
# of a `<` after its `)`. Each of these tokens starts an expression, or binds more loosely than
# `<` (SPEC.md §3.2).
BEFORE_GROUP: frozenset[Op | Keyword] = ASSIGN_OPS | {
    Op.LPAREN, Op.LBRACE, Op.COMMA, Op.ANDAND, Op.OROR, Keyword.RETURN, Keyword.IF,
    Keyword.WHILE}
# The operators that bind no more tightly than `<` (SPEC.md §3.2).
LOOSE_OPS: frozenset[Op] = COMPARISONS | {Op.ANDAND, Op.OROR}
# Names that Fe reads as a pattern of a variant of `Option`, which is in scope in every program
# (SPEC.md §5.2).
VARIANT_NAMES: tuple[FeName, ...] = (FeName("Some"), FeName("None"))
# The word after one of these keywords is the name of a constant, the contract or an event. A
# local may not take such a name (N018). Fe reads it as a pattern and rejects it
# (SPEC.md §5.2).
PATTERN_DECLARERS: frozenset[Keyword] = frozenset({
    Keyword.CONST, Keyword.CONTRACT, Keyword.STRUCT})
# No program of the corpus or of gen.py uses this name, so a local of this name hides nothing
# that a later line uses.
UNREACHABLE_LOCAL = FeName("mutant_unreachable")


class Text(NamedTuple):
    """A program with its tokens, whose offsets index `data`."""

    data: bytes
    # Every token, trivia included.
    toks: list[Token]
    sig: list[Token]

    @classmethod
    def of(cls, source: FeSource) -> "Text":
        data = source.encode()
        toks = list(tokens(data))
        return cls(data, toks, significant(toks))


def reflow(text: Text, rng: random.Random) -> FeSource:
    """Returns `text` with a line break in about half of the places inside parentheses where
    Fe0 allows one: after a `(`, a `,` or a binary operator, and before a `)`."""
    breaks: list[Edit] = []
    # The open brackets.
    stack: list[Token] = []
    prev: Token | None = None

    def maybe_break(start: ByteOffset, end: ByteOffset) -> None:
        """Adds to `breaks` an edit that puts a line break in place of `text.data[start:end]`,
        half of the time."""
        if stack and stack[-1].symbol == Op.LPAREN and rng.random() < 0.5:
            breaks.append(Edit(start, end, b"\n"))

    for t in text.toks:
        match t.kind:
            case Kind.OPEN:
                stack.append(t)
                maybe_break(t.end, t.end)
            case Kind.CLOSE:
                maybe_break(t.start, t.start)
                stack.pop()
            case Kind.SPACE if prev is not None and (prev.symbol == Op.COMMA
                                                     or prev.symbol in BINARY_OPS):
                maybe_break(t.start, t.end)
        if not t.kind.trivia:
            prev = t
    return apply_edits(text.data, breaks)


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
    UNPAREN = "unparen"
    TYPE_NAME = "type_name"
    CHAIN = "chain"
    CONST_CYCLE = "const_cycle"
    DROP_MUT = "drop_mut"
    DROP_USES = "drop_uses"
    BOOL_FOR_INT = "bool_for_int"
    PATTERN_NAME = "pattern_name"

    @property
    def expect(self) -> Expect:
        match self:
            case Mutation.UNREACHABLE:
                return Expect.ANY_CODE
            case (Mutation.COMMENT | Mutation.SPACE | Mutation.PAREN | Mutation.REFLOW
                  | Mutation.RENAME | Mutation.UNPAREN):
                return Expect.SAME_CODE
            case (Mutation.TYPE_NAME | Mutation.CHAIN | Mutation.CONST_CYCLE | Mutation.DROP_MUT
                  | Mutation.DROP_USES | Mutation.BOOL_FOR_INT | Mutation.PATTERN_NAME):
                return Expect.REJECT

    @property
    def breaks_rule(self) -> bool:
        """True if the mutation is rule-breaking (task Tdf1kp, "Three families of mutation").
        False otherwise."""
        return self.expect == Expect.REJECT

    def mutate(self, text: Text, rng: random.Random) -> FeSource | None:
        """Returns a mutant of `text`, or None when `text` has no place for the mutation."""
        match self:
            case Mutation.COMMENT:
                return comment(text, rng)
            case Mutation.SPACE:
                return space(text, rng)
            case Mutation.PAREN:
                return paren(text, rng)
            case Mutation.REFLOW:
                return reflow(text, rng)
            case Mutation.RENAME:
                return rename(text, rng)
            case Mutation.UNREACHABLE:
                return unreachable(text, rng)
            case Mutation.UNPAREN:
                return unparen(text, rng)
            case Mutation.TYPE_NAME:
                return type_name(text, rng)
            case Mutation.CHAIN:
                return chain(text, rng)
            case Mutation.CONST_CYCLE:
                return const_cycle(text, rng)
            case Mutation.DROP_MUT:
                return drop_mut(text, rng)
            case Mutation.DROP_USES:
                return drop_uses(text, rng)
            case Mutation.BOOL_FOR_INT:
                return bool_for_int(text, rng)
            case Mutation.PATTERN_NAME:
                return pattern_name(text, rng)


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
        return apply_edits(data, [self])


def apply_edits(data: bytes, edits: Iterable[Edit]) -> FeSource:
    """Returns `data` with each of `edits` made, for edits that are in order and do not
    overlap."""
    out = bytearray()
    last = ByteOffset(0)
    for e in edits:
        out += data[last:e.start] + e.text
        last = e.end
    return FeSource((out + data[last:]).decode())


def comment(text: Text, rng: random.Random) -> FeSource | None:
    """Returns `text` with a plain comment at the end of a line, or with a plain comment line
    after it. Returns None when `text` has no line end."""
    ends = [t for t in text.toks if t.kind == Kind.NEWLINE]
    if not ends:
        return None
    t = rng.choice(ends)
    edit = Edit(t.start, t.start, b" // mutant") if rng.random() < 0.5 else \
        Edit(t.end, t.end, b"// mutant" + t.text)
    return edit.apply(text.data)


def space(text: Text, rng: random.Random) -> FeSource | None:
    """Returns `text` with a space between two adjacent tokens on one line. Returns None when no
    two tokens touch."""
    joints = [b.start for a, b in zip(text.toks, text.toks[1:])
              if not a.kind.trivia and a.kind != Kind.NEWLINE
              and b.kind not in (Kind.SPACE, Kind.NEWLINE)]
    if not joints:
        return None
    at = rng.choice(joints)
    return Edit(at, at, b" ").apply(text.data)


def declared(sig: list[Token]) -> set[FeName]:
    """Returns the names that a program declares: each word after `let`, `var`, `const` or
    `mut`, and each word before a parameter's `:`."""
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


def paren(text: Text, rng: random.Random) -> FeSource | None:
    """Returns `text` with parentheses around one operand that is an integer literal, `true`,
    `false` or a name the program declares (task Tdf1kp). Returns None when there is no such
    operand."""
    names = declared(text.sig)
    atoms = operands(text.sig,
                     lambda t: t.kind == Kind.NUMBER or t.symbol in BOOLS or t.word in names)
    if not atoms:
        return None
    t = rng.choice(atoms)
    wrapped = Op.LPAREN.encode() + t.text + Op.RPAREN.encode()
    return Edit(t.start, t.end, wrapped).apply(text.data)


def named_after(sig: list[Token], keywords: frozenset[Keyword]) -> list[FeName]:
    """Returns the words that come right after one of `keywords`, sorted."""
    return sorted({w for a, b in zip(sig, sig[1:]) if a.symbol in keywords and (w := b.word)})


def rename_word(text: Text, old: FeName, new: FeName) -> FeSource:
    """Returns `text` with every word `old` changed to `new`."""
    return apply_edits(text.data, [Edit(t.start, t.end, new.encode()) for t in text.toks
                                   if t.word == old])


def rename_local(text: Text, rng: random.Random, names: Sequence[FeName]) -> FeSource | None:
    """Returns `text` with one local's name, at every place it appears, changed to one of
    `names`. Returns None when the program has no local or `names` is empty."""
    locals_ = named_after(text.sig, LOCAL_DECLARERS)
    if not locals_ or not names:
        return None
    return rename_word(text, rng.choice(locals_), rng.choice(names))


def rename(text: Text, rng: random.Random) -> FeSource | None:
    """Returns `text` with one local renamed, at every place it appears, to a name that Fe and
    Fe0 both allow for a local (task Tdf1kp, "Three families of mutation"). Returns None when
    the program has no local, or when each such name already names a local, a parameter, a
    constant or a field."""
    taken = declared(text.sig)
    hideable = [n for n in named_after(text.sig, HIDEABLE_DECLARERS) if n[:1].islower()]
    return rename_local(text, rng, sorted(n for n in {*ODD_NAMES, *hideable} if n not in taken))


def type_name(text: Text, rng: random.Random) -> FeSource | None:
    """Returns `text` with one local's name, at every place it appears, changed to a type
    name. Returns None when the program has no local."""
    return rename_local(text, rng, TYPE_NAMES)


def pattern_name(text: Text, rng: random.Random) -> FeSource | None:
    """Returns `text` with one local's name, at every place it appears, changed to a name that
    Fe reads as a pattern, as VARIANT_NAMES and PATTERN_DECLARERS say. Returns None when the
    program has no local."""
    return rename_local(text, rng,
                        sorted({*VARIANT_NAMES, *named_after(text.sig, PATTERN_DECLARERS)}))


def chain(text: Text, rng: random.Random) -> FeSource | None:
    """Returns `text` with ` < 1` after the right operand of a comparison, so that the `bool`
    the comparison gives is ordered. Fe rejects that, because `bool` has no `Ord`
    (SPEC.md §3.2). Returns None when no comparison has an atom on its right."""
    rights = [b for a, b, c in zip(text.sig, text.sig[1:], text.sig[2:])
              if a.symbol in COMPARISONS and b.kind in (Kind.WORD, Kind.NUMBER)
              and (ends_operand(c) or c.symbol == Op.LBRACE)]
    if not rights:
        return None
    t = rng.choice(rights)
    return Edit(t.end, t.end, b" < 1").apply(text.data)


def statement_end(toks: list[Token], i: TokenIndex) -> Token | None:
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


def const_cycle(text: Text, rng: random.Random) -> FeSource | None:
    """Returns `text` with one constant's value replaced by the constant itself. Returns None
    when the program has no constant."""
    toks = [t for t in text.toks if t.kind != Kind.COMMENT]
    edits = []
    for i, t in enumerate(toks):
        if t.symbol != Keyword.CONST:
            continue
        n = next_index(toks, TokenIndex(i), lambda u: not u.kind.trivia)
        j = next_index(toks, TokenIndex(i), lambda u: u.symbol == Op.ASSIGN)
        if n is not None and j is not None and (end := statement_end(toks, j)) is not None:
            edits.append(Edit(toks[j].end, end.start, b" " + toks[n].text))
    return rng.choice(edits).apply(text.data) if edits else None


class UsesClause(NamedTuple):
    # The tokens from the space before `uses`, when there is one, to the `)` that closes the
    # clause's list.
    toks: Sequence[Token]

    def cut(self) -> Edit:
        """Returns the edit that takes the clause out."""
        return Edit(self.toks[0].start, self.toks[-1].end, b"")

    def mut_cuts(self) -> list[Edit]:
        """Returns, for each `mut` in the clause's list, the edit that takes it out with the
        space after it."""
        return [Edit(a.start, b.end, b"") for a, b in zip(self.toks, self.toks[1:])
                if a.symbol == Keyword.MUT and b.kind == Kind.SPACE]


def uses_clauses(toks: list[Token]) -> list[UsesClause]:
    """Returns each `uses` clause of `toks`."""
    brackets = Brackets(toks)
    out = []
    for i, t in enumerate(toks):
        if t.symbol != Keyword.USES:
            continue
        o = next_index(toks, TokenIndex(i), lambda u: u.kind == Kind.OPEN)
        if o is not None and (close := brackets.close(o)) is not None:
            first = i - 1 if toks[i - 1].kind == Kind.SPACE else i
            out.append(UsesClause(toks[first:close + 1]))
    return out


def drop_mut(text: Text, rng: random.Random) -> FeSource | None:
    """Returns `text` with one `mut` taken out of a `uses` list. Returns None when no `uses`
    list has a `mut`."""
    cuts = [e for u in uses_clauses(text.toks) for e in u.mut_cuts()]
    return rng.choice(cuts).apply(text.data) if cuts else None


def drop_uses(text: Text, rng: random.Random) -> FeSource | None:
    """Returns `text` with one `uses` list taken out. Returns None when it has none."""
    cuts = [u.cut() for u in uses_clauses(text.toks)]
    return rng.choice(cuts).apply(text.data) if cuts else None


def bool_for_int(text: Text, rng: random.Random) -> FeSource | None:
    """Returns `text` with `true` in place of one integer literal that is an operand. Returns
    None when it has none."""
    atoms = operands(text.sig, lambda t: t.kind == Kind.NUMBER)
    if not atoms:
        return None
    t = rng.choice(atoms)
    return Edit(t.start, t.end, Keyword.TRUE.encode()).apply(text.data)


def guards_generics(brackets: Brackets, pair: BracketPair) -> bool:
    """Checks whether `pair` is one that gen.py adds when `E.may_take_generics` holds. Such a
    pair holds the whole left operand of a `<`, and the operand ends with a name or a literal
    and stays on one line."""
    before = brackets.toks[pair.open - 1]
    return ((before.kind == Kind.NEWLINE or before.symbol in BEFORE_GROUP)
            and brackets.toks[pair.close + 1].symbol == Op.LT
            and brackets.toks[pair.close - 1].kind in (Kind.WORD, Kind.NUMBER)
            and not any(t.symbol in LOOSE_OPS or t.kind == Kind.NEWLINE
                        for t in brackets.top_level(pair)))


def guards_record(brackets: Brackets, pair: BracketPair) -> bool:
    """Checks whether `pair` is one that gen.py adds when `E.may_read_as_record` holds. Such a
    pair holds a block. The `(` starts a line, and the `)` ends one."""
    after = brackets.toks[pair.close + 1]
    return (brackets.toks[pair.open - 1].kind == Kind.NEWLINE
            and brackets.toks[pair.open + 1].symbol == Op.LBRACE
            and brackets.close(TokenIndex(pair.open + 1)) == pair.close - 1
            and (after.kind == Kind.NEWLINE or after.symbol == Op.RBRACE))


def added_by_gen(brackets: Brackets, pair: BracketPair) -> bool:
    """Checks whether `pair` is a pair of parentheses that gen.py adds."""
    return (brackets.toks[pair.open].symbol == Op.LPAREN
            and pair.open > 0 and pair.close + 1 < len(brackets.toks)
            and (guards_generics(brackets, pair) or guards_record(brackets, pair)))


def unparen(text: Text, rng: random.Random) -> FeSource | None:
    """Returns `text` without one pair of the parentheses that gen.py adds (task Tdf1kp,
    "`unparen` is meaning-preserving"). Returns None when `text` has no such pair."""
    brackets = Brackets(text.sig)
    cuts = [[Edit(t.start, t.end, b"") for t in (brackets.toks[p.open], brackets.toks[p.close])]
            for p in brackets if added_by_gen(brackets, p)]
    return apply_edits(text.data, rng.choice(cuts)) if cuts else None


def unreachable(text: Text, rng: random.Random) -> FeSource | None:
    """Returns `text` with a `let` statement right after a `return` statement, in the same
    block (task Tdf1kp). Returns None when no `return` ends its line in its block."""
    ends = [end for i, t in enumerate(text.toks) if t.symbol == Keyword.RETURN
            and (end := statement_end(text.toks, TokenIndex(i))) is not None]
    if not ends:
        return None
    t = rng.choice(ends)
    line = f"let {UNREACHABLE_LOCAL}: u256 = 0".encode()
    return Edit(t.end, t.end, line + t.text).apply(text.data)


def mutants(source: FeSource, rng: random.Random, count: int) -> list[Mutant]:
    """Returns `count` mutants of `source`, or fewer when a mutation finds no place."""
    text = Text.of(source)
    out = []
    for _ in range(count):
        mutation = rng.choice(list(Mutation))
        if (mutant := mutation.mutate(text, rng)) is not None:
            out.append(Mutant(mutation, mutant))
    return out


def known_narrowings() -> set[DiagCode]:
    """Returns the codes of the reject programs that Fe accepts, which SPEC.md states as
    narrowings of Fe's rules. A mutant that Fe accepts and Fe0 rejects with one of these codes
    is not a finding, even when its case is not the one that the reject program shows."""
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


class Finding(NamedTuple):
    """A mutant that task Tdf1kp counts as a finding."""

    # The mutant's path, relative to the repo root.
    path: Path
    says: str

    def __str__(self) -> str:
        return f"{self.path}: {self.says}"


def finding(m: Mutant, original: Original, path: Path,
            known: set[DiagCode]) -> Finding | Agreement:
    """Checks the mutant at `path` with both compilers, and returns the finding, or how the
    compilers agree when there is none."""
    rel = path.relative_to(ROOT)
    run = cli_check.Run.of(rel, m.source)
    fe = embed.fe_rejection(rel)
    if run.compiled():
        if fe is not None:
            return Finding(rel, f"Fe rejects it and Fe0 accepts it\n{fe.rstrip()}")
        if m.mutation.breaks_rule:
            return Agreement.MISSED
        if m.mutation.expect == Expect.SAME_CODE and run.program().code != original.code:
            return Finding(rel, f"Fe0 compiles it to other bytes than {original.path}")
        return Agreement.ACCEPTED
    if fe is not None:
        return Agreement.BOTH_REJECT
    error = run.error()
    if error is None:
        return Finding(rel, f"Fe0 does not compile it cleanly: {run.said()}")
    if error.code in known:
        return Agreement.KNOWN_NARROWING
    return Finding(rel, f"Fe accepts it and Fe0 rejects it: {error.describe(m.source)}")


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
    findings: list[Finding] = []
    agreements: Counter[tuple[Agreement, Mutation]] = Counter()
    checked = 0
    for original in originals(args.seed, args.n):
        rng = random.Random(f"{args.seed}:{original.path.stem}")
        for i, m in enumerate(mutants(original.source, rng, args.per_program)):
            path = OUT / f"{original.path.stem}_{m.mutation}_{i}.fe"
            path.write_text(m.source)
            checked += 1
            match finding(m, original, path, known):
                case Finding() as found:
                    print(found, flush=True)
                    findings.append(found)
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
