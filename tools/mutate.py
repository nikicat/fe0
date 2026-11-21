#!/usr/bin/env python3
"""Mutate accepted programs and check each mutant with Fe0's native CLI and with `fe check`.

The programs are corpus/*.fe and the generated programs of the seeds. The same seed always gives
the same mutants. Each mutant is written to out/mutate/, so a finding can be read there. The
tool prints each finding and a summary, and exits with 1 when it finds one. DESIGN.md §11a
says what counts as a finding and which families of mutation there are.

usage: mutate.py [--seed N] [-n N] [--per-program N]
"""
import argparse
import random
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from enum import Enum, StrEnum, auto
from pathlib import Path
from typing import NamedTuple

import cli_check
import embed
from fegen import ROOT, ByteOffset, DiagCode, FeName, FeSource
from fetokens import (ASSIGN_OPS, BracketPair, Brackets, Keyword, Kind, Op, Token, TokenIndex,
                      next_index, significant, tokens)
from gen import GEN, Gen, Seed, program_file, seeds_from

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
# An uppercase name that is no type or variant, so Fe accepts it for a local (SPEC.md §5.2).
UPPER_LOCAL_NAME = FeName("MutantLocal")
# A `let` whose local has the name of its own type, `u256`. Fe accepts it while no later line
# uses the local (SPEC.md §1, "Type names").
OWN_TYPE_LET = b"let u256: u256 = 0"
FN_VALUE_LOCAL = FeName("mutant_fn")
SECOND_CONTRACT_SOURCE = b"contract MutantSecond {\n    mut w: u256,\n}\n"
MAP_TYPE = FeName("StorageMap")


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

    def apply_one(self, rng: random.Random, changes: Sequence[Change]) -> FeSource | None:
        """Returns `data` with one of `changes` made. `rng` picks which. Returns None when
        `changes` is empty."""
        if not changes:
            return None
        change = rng.choice(changes)
        return apply_edits(self.data, [change] if isinstance(change, Edit) else change)


def reflow(text: Text, rng: random.Random) -> FeSource:
    """Returns `text` with a line break in about half of the places inside parentheses where
    Fe0 allows one: after a `(`, a `,` or a binary operator, and before a `)`."""
    breaks: list[Edit] = []
    brackets = Brackets(text.toks)
    prev: Token | None = None

    def maybe_break(i: TokenIndex, start: ByteOffset, end: ByteOffset) -> None:
        """Adds to `breaks` an edit that puts a line break in place of `text.data[start:end]`,
        half of the time, when `text.toks[i]` is inside parentheses."""
        if brackets.in_parens(i) and rng.random() < 0.5:
            breaks.append(Edit(start, end, b"\n"))

    for i, t in enumerate(text.toks):
        match t.kind:
            case Kind.OPEN:
                maybe_break(TokenIndex(i), t.end, t.end)
            case Kind.CLOSE:
                maybe_break(TokenIndex(i), t.start, t.start)
            case Kind.SPACE if prev is not None and (prev.symbol == Op.COMMA
                                                     or prev.symbol in BINARY_OPS):
                maybe_break(TokenIndex(i), t.start, t.end)
        if not t.kind.trivia:
            prev = t
    return apply_edits(text.data, breaks)


class Expect(Enum):
    """What the tool expects of a mutant, by its mutation's family (DESIGN.md §11a, "Three
    families of mutation")."""

    SAME_CODE = "same code"
    ANY_CODE = "any code"
    REJECT = "reject"
    NARROWING = "narrowing"


class Mutation(StrEnum):
    """A meaning-preserving, rule-breaking or narrowing mutation (DESIGN.md §11a, "Three
    families of mutation")."""

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
    UPPER_LOCAL = "upper_local"
    OWN_TYPE_LOCAL = "own_type_local"
    FN_VALUE = "fn_value"
    IF_CONST = "if_const"
    SECOND_CONTRACT = "second_contract"
    BREAK_BEFORE_OP = "break_before_op"
    PAREN_MAP = "paren_map"
    MAP_GET = "map_get"

    @property
    def expect(self) -> Expect:
        if self.probe is not None:
            return Expect.NARROWING
        match self:
            case Mutation.UNREACHABLE:
                return Expect.ANY_CODE
            case (Mutation.COMMENT | Mutation.SPACE | Mutation.PAREN | Mutation.REFLOW
                  | Mutation.RENAME | Mutation.UNPAREN):
                return Expect.SAME_CODE
            case (Mutation.TYPE_NAME | Mutation.CHAIN | Mutation.CONST_CYCLE | Mutation.DROP_MUT
                  | Mutation.DROP_USES | Mutation.BOOL_FOR_INT | Mutation.PATTERN_NAME):
                return Expect.REJECT
            case _:
                raise AssertionError(f"{self} is in no family of mutation")

    @property
    def probe(self) -> Path | None:
        """The reject program whose construct a narrowing mutation plants (DESIGN.md §11a). None
        for a mutation of another family."""
        match self:
            case Mutation.UPPER_LOCAL:
                return embed.REJECTS / "uppercase_let_not_a_type.fe"
            case Mutation.OWN_TYPE_LOCAL:
                return embed.REJECTS / "type_name_unused_let.fe"
            case Mutation.FN_VALUE:
                return embed.REJECTS / "fn_as_value.fe"
            case Mutation.IF_CONST:
                return embed.REJECTS / "if_in_const.fe"
            case Mutation.SECOND_CONTRACT:
                return embed.REJECTS / "two_contracts.fe"
            case Mutation.BREAK_BEFORE_OP:
                return embed.REJECTS / "line_break_plus.fe"
            case Mutation.PAREN_MAP:
                return embed.REJECTS / "map_paren_map.fe"
            case Mutation.MAP_GET:
                return embed.REJECTS / "map_get_method.fe"
            case _:
                return None

    @property
    def breaks_rule(self) -> bool:
        """True if the mutation is rule-breaking (DESIGN.md §11a, "Three families of mutation").
        False otherwise."""
        return self.expect == Expect.REJECT

    def mutate(self, text: Text, rng: random.Random) -> FeSource | None:
        """Returns a mutant of `text`. `rng` picks the change, or for REFLOW the line breaks.
        Returns None when `text` has no place for the mutation."""
        changes: Sequence[Change]
        match self:
            case Mutation.REFLOW:
                return reflow(text, rng)
            case Mutation.COMMENT:
                changes = comment(text)
            case Mutation.SPACE:
                changes = space(text)
            case Mutation.PAREN:
                changes = paren(text)
            case Mutation.RENAME:
                changes = rename(text)
            case Mutation.UNREACHABLE:
                changes = unreachable(text)
            case Mutation.UNPAREN:
                changes = unparen(text)
            case Mutation.TYPE_NAME:
                changes = type_name(text)
            case Mutation.CHAIN:
                changes = chain(text)
            case Mutation.CONST_CYCLE:
                changes = const_cycle(text)
            case Mutation.DROP_MUT:
                changes = drop_mut(text)
            case Mutation.DROP_USES:
                changes = drop_uses(text)
            case Mutation.BOOL_FOR_INT:
                changes = bool_for_int(text)
            case Mutation.PATTERN_NAME:
                changes = pattern_name(text)
            case Mutation.UPPER_LOCAL:
                changes = rename_local(text, [UPPER_LOCAL_NAME])
            case Mutation.OWN_TYPE_LOCAL:
                changes = before_let(text, OWN_TYPE_LET)
            case Mutation.FN_VALUE:
                changes = fn_value(text)
            case Mutation.IF_CONST:
                changes = if_const(text)
            case Mutation.SECOND_CONTRACT:
                changes = second_contract(text)
            case Mutation.BREAK_BEFORE_OP:
                changes = break_before_op(text)
            case Mutation.PAREN_MAP:
                changes = paren_map(text)
            case Mutation.MAP_GET:
                changes = map_get(text)
        return text.apply_one(rng, changes)


class Mutant(NamedTuple):
    """A program that one mutation changed."""

    mutation: Mutation
    source: FeSource


class Edit(NamedTuple):
    """Bytes that replace `data[start:end]`."""

    start: ByteOffset
    end: ByteOffset
    text: bytes

    @classmethod
    def replacing(cls, t: Token, text: bytes) -> "Edit":
        """Returns the edit that puts `text` in place of `t`."""
        return cls(t.start, t.end, text)


# One change that a mutation can make to a program: one edit, or several edits in order.
type Change = Edit | Sequence[Edit]


def parenthesized(t: Token) -> Edit:
    """Returns the edit that puts parentheses around `t`."""
    return Edit.replacing(t, Op.LPAREN.encode() + t.text + Op.RPAREN.encode())


def apply_edits(data: bytes, edits: Iterable[Edit]) -> FeSource:
    """Returns `data` with each of `edits` made, for edits that are in order and do not
    overlap."""
    out = bytearray()
    last = ByteOffset(0)
    for e in edits:
        out += data[last:e.start] + e.text
        last = e.end
    return FeSource((out + data[last:]).decode())


def comment(text: Text) -> list[Edit]:
    """Returns the edits that put a plain comment at the end of a line, and those that put a
    plain comment line after it. Empty when `text` has no line end."""
    return [e for t in text.toks if t.kind == Kind.NEWLINE
            for e in (Edit(t.start, t.start, b" // mutant"),
                      Edit(t.end, t.end, b"// mutant" + t.text))]


def space(text: Text) -> list[Edit]:
    """Returns the edits that put a space between two adjacent tokens on one line. Empty when no
    two tokens touch."""
    joints = [b.start for a, b in zip(text.toks, text.toks[1:])
              if not a.kind.trivia and a.kind != Kind.NEWLINE
              and b.kind not in (Kind.SPACE, Kind.NEWLINE)]
    return [Edit(at, at, b" ") for at in joints]


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


def paren(text: Text) -> list[Edit]:
    """Returns the edits that put parentheses around one operand that is an integer literal,
    `true`, `false` or a name the program declares (DESIGN.md §11a). Empty when there is no such
    operand."""
    names = declared(text.sig)
    atoms = operands(text.sig,
                     lambda t: t.kind == Kind.NUMBER or t.symbol in BOOLS or t.word in names)
    return [parenthesized(t) for t in atoms]


def named_after(sig: list[Token], keywords: frozenset[Keyword]) -> list[FeName]:
    """Returns the words that come right after one of `keywords`, sorted."""
    return sorted({w for a, b in zip(sig, sig[1:]) if a.symbol in keywords and (w := b.word)})


def rename_word(text: Text, old: FeName, new: FeName) -> list[Edit]:
    """Returns the edits that change every word `old` to `new`."""
    return [Edit.replacing(t, new.encode()) for t in text.toks if t.word == old]


def rename_local(text: Text, names: Sequence[FeName]) -> list[list[Edit]]:
    """Returns, for each local and each of `names`, the edits that change the local's name to
    that name at every place it appears. Empty when the program has no local or `names` is
    empty."""
    return [rename_word(text, old, new)
            for old in named_after(text.sig, LOCAL_DECLARERS) for new in names]


def rename(text: Text) -> list[list[Edit]]:
    """Returns the changes that each rename one local, everywhere it appears, to a name that Fe
    and Fe0 both allow for a local (DESIGN.md §11a, "Three families of mutation"). Empty when
    the program has no local, or when each such name already names a local, a parameter, a
    constant or a field."""
    taken = declared(text.sig)
    hideable = [n for n in named_after(text.sig, HIDEABLE_DECLARERS) if n[:1].islower()]
    return rename_local(text, sorted(n for n in {*ODD_NAMES, *hideable} if n not in taken))


def type_name(text: Text) -> list[list[Edit]]:
    """Returns the changes that each rename one local, everywhere it appears, to a type name.
    Empty when the program has no local."""
    return rename_local(text, TYPE_NAMES)


def pattern_name(text: Text) -> list[list[Edit]]:
    """Returns the changes that each rename one local, everywhere it appears, to a name that Fe
    reads as a pattern, as VARIANT_NAMES and PATTERN_DECLARERS say. Empty when the program
    has no local."""
    return rename_local(text,
                        sorted({*VARIANT_NAMES, *named_after(text.sig, PATTERN_DECLARERS)}))


def chain(text: Text) -> list[Edit]:
    """Returns the edits that put ` < 1` after the right operand of a comparison, so that the
    `bool` the comparison gives is ordered. Fe rejects that, because `bool` has no `Ord`
    (SPEC.md §3.2). Empty when no comparison has an atom on its right."""
    rights = [b for a, b, c in zip(text.sig, text.sig[1:], text.sig[2:])
              if a.symbol in COMPARISONS and b.kind in (Kind.WORD, Kind.NUMBER)
              and (ends_operand(c) or c.symbol == Op.LBRACE)]
    return [Edit(t.end, t.end, b" < 1") for t in rights]


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


class ConstValue(NamedTuple):
    """A constant's value spans from right after its `=` to the end of its statement."""

    name: Token
    start: ByteOffset
    end: ByteOffset
    # The bytes of the span, without the space around them.
    value: bytes

    def replace(self, new: bytes) -> Edit:
        """Returns the edit that makes `new` the constant's value."""
        return Edit(self.start, self.end, b" " + new)


def const_values(text: Text) -> list[ConstValue]:
    """Returns the value of each constant of `text`."""
    toks = [t for t in text.toks if t.kind != Kind.COMMENT]
    out = []
    for i, t in enumerate(toks):
        if t.symbol != Keyword.CONST:
            continue
        n = next_index(toks, TokenIndex(i), lambda u: not u.kind.trivia)
        j = next_index(toks, TokenIndex(i), lambda u: u.symbol == Op.ASSIGN)
        if n is not None and j is not None and (end := statement_end(toks, j)) is not None:
            start, stop = toks[j].end, end.start
            out.append(ConstValue(toks[n], start, stop, text.data[start:stop].strip()))
    return out


def const_cycle(text: Text) -> list[Edit]:
    """Returns the edits that replace one constant's value by the constant itself. Empty when
    the program has no constant."""
    return [c.replace(c.name.text) for c in const_values(text)]


def if_const(text: Text) -> list[Edit]:
    """Returns the edits that replace one constant's value `V` by `if true { V } else { V }`.
    Empty when the program has no constant."""
    return [c.replace(b"if true { " + c.value + b" } else { " + c.value + b" }")
            for c in const_values(text)]


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


def drop_mut(text: Text) -> list[Edit]:
    """Returns the edits that take one `mut` out of a `uses` list. Empty when no `uses` list
    has a `mut`."""
    return [e for u in uses_clauses(text.toks) for e in u.mut_cuts()]


def drop_uses(text: Text) -> list[Edit]:
    """Returns the edits that take one `uses` list out. Empty when `text` has none."""
    return [u.cut() for u in uses_clauses(text.toks)]


def bool_for_int(text: Text) -> list[Edit]:
    """Returns the edits that put `true` in place of one integer literal that is an operand.
    Empty when `text` has none."""
    atoms = operands(text.sig, lambda t: t.kind == Kind.NUMBER)
    return [Edit.replacing(t, Keyword.TRUE.encode()) for t in atoms]


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


def unparen(text: Text) -> list[list[Edit]]:
    """Returns, for each pair of the parentheses that gen.py adds, the edits that drop it
    (DESIGN.md §11a, "`unparen` drops only parentheses of the two shapes that gen.py adds").
    Empty when `text` has no such pair."""
    brackets = Brackets(text.sig)
    return [[Edit.replacing(brackets.toks[i], b"") for i in (p.open, p.close)]
            for p in brackets if added_by_gen(brackets, p)]


def unreachable(text: Text) -> list[Edit]:
    """Returns the edits that put a `let` statement right after a `return` statement, in the
    same block. Empty when no `return` ends its line in its block."""
    ends = [end for i, t in enumerate(text.toks) if t.symbol == Keyword.RETURN
            and (end := statement_end(text.toks, TokenIndex(i))) is not None]
    line = f"let {UNREACHABLE_LOCAL}: u256 = 0".encode()
    return [Edit(t.end, t.end, line + t.text) for t in ends]


def before_let(text: Text, line: bytes) -> list[Edit]:
    """Returns the edits that put `line` as a statement of its own right before one `let`
    statement that starts its line. Empty when no `let` starts a line."""
    return [Edit(t.start, t.start, line + nl.text + indent.text)
            for nl, indent, t in zip(text.toks, text.toks[1:], text.toks[2:])
            if nl.kind == Kind.NEWLINE and indent.kind == Kind.SPACE
            and t.symbol == Keyword.LET]


def fn_value(text: Text) -> list[Edit]:
    """Returns the edits that put a `let` that binds one function right before one `let`
    statement. Empty when the program has no function or no `let` that starts a line."""
    return [e for f in named_after(text.sig, frozenset({Keyword.FN}))
            for e in before_let(text, f"let {FN_VALUE_LOCAL} = {f}".encode())]


def second_contract(text: Text) -> list[Edit]:
    """Returns the edit that puts a second contract at the end of `text`. Empty when `text` has
    no contract."""
    if not any(t.symbol == Keyword.CONTRACT for t in text.sig):
        return []
    end = ByteOffset(len(text.data))
    nl = b"" if text.data.endswith(b"\n") else b"\n"
    return [Edit(end, end, nl + SECOND_CONTRACT_SOURCE)]


def break_before_op(text: Text) -> list[Edit]:
    """Returns the edits that put a line break, inside parentheses, in place of the space
    between an operand and a binary operator. Empty when there is no such space."""
    brackets = Brackets(text.toks)
    breaks = [Edit.replacing(b, b"\n")
              for i, (a, b, c) in enumerate(zip(text.toks, text.toks[1:], text.toks[2:]), 1)
              if b.kind == Kind.SPACE and brackets.in_parens(TokenIndex(i))
              and a.kind in (Kind.WORD, Kind.NUMBER, Kind.CLOSE) and c.symbol in BINARY_OPS]
    return breaks


def map_indexes(sig: list[Token]) -> list[TokenIndex]:
    """Returns the index in `sig` of the `[` of each entry `m[k]` of a contract's map field."""
    maps = {w for a, b, c in zip(sig, sig[1:], sig[2:])
            if (w := a.word) and b.symbol == Op.COLON and c.word == MAP_TYPE}
    return [TokenIndex(i + 1) for i, (a, b) in enumerate(zip(sig, sig[1:]))
            if a.word in maps and b.symbol == Op.LBRACKET]


def paren_map(text: Text) -> list[Edit]:
    """Returns the edits that put parentheses around the map of one entry `m[k]`. Empty when
    `text` reads no map entry."""
    return [parenthesized(text.sig[o - 1]) for o in map_indexes(text.sig)]


def map_get(text: Text) -> list[list[Edit]]:
    """Returns, for each entry `m[k]` that is read, not written or indexed again, the edits
    that replace it by `m.get(k)`. Empty when `text` reads no such entry."""
    brackets = Brackets(text.sig)
    reads = []
    for o in map_indexes(text.sig):
        close = brackets.close(o)
        if close is None or close + 1 >= len(text.sig):
            continue
        after = text.sig[close + 1].symbol
        if after not in ASSIGN_OPS and after != Op.LBRACKET:
            reads.append([Edit.replacing(text.sig[o], b".get("),
                          Edit.replacing(text.sig[close], b")")])
    return reads


def mutants(source: FeSource, rng: random.Random, count: int) -> list[Mutant]:
    """Returns `count` mutants of `source`, or fewer when a mutation finds no place."""
    text = Text.of(source)
    out = []
    for _ in range(count):
        mutation = rng.choice(list(Mutation))
        if (mutant := mutation.mutate(text, rng)) is not None:
            out.append(Mutant(mutation, mutant))
    return out


class Probe(NamedTuple):
    """A reject program that shows a narrowing (DESIGN.md §11a)."""

    # The program's path, relative to the repo root.
    path: Path
    code: DiagCode


class Narrowings(NamedTuple):
    """The narrowings that the reject programs show (DESIGN.md §11a)."""

    # The codes of the probes.
    known: frozenset[DiagCode]
    # The probe that each narrowing mutation plants.
    planted: Mapping[Mutation, Probe]

    @classmethod
    def load(cls) -> "Narrowings":
        """Returns the narrowings that the reject programs show. Errors with ValueError when the
        reject program that a mutation plants has no `// fe: accepts` line. Exits with a message
        when a reject program does not load."""
        rejects = {r.path: r for r in embed.load_rejects()}
        planted = {}
        for m in Mutation:
            if (path := m.probe) is not None:
                r = rejects[path.relative_to(ROOT)]
                if not r.fe_accepts:
                    raise ValueError(f"{r.path}, the probe of {m}, has no `fe: accepts` line")
                planted[m] = Probe(r.path, r.expected.code)
        known = frozenset(r.expected.code for r in rejects.values() if r.fe_accepts)
        return cls(known, planted)


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
    """A mutant that DESIGN.md §11a counts as a finding."""

    # The mutant's path, relative to the repo root.
    path: Path
    says: str

    def __str__(self) -> str:
        return f"{self.path}: {self.says}"


def classify(m: Mutant, original: Original, run: cli_check.Run, fe: str | None,
             narrowings: Narrowings) -> Finding | Agreement:
    """Classifies the mutant by what Fe0 did with it (`run`) and Fe's rejection of it (`fe`,
    None when Fe accepts it). Returns a finding as DESIGN.md §11a counts one, or how the
    compilers agree when there is none."""
    probe = narrowings.planted.get(m.mutation)
    if run.compiled():
        if fe is not None:
            return Finding(run.path, f"Fe rejects it and Fe0 accepts it\n{fe.rstrip()}")
        if m.mutation.breaks_rule:
            return Agreement.MISSED
        if probe is not None:
            return Finding(run.path, f"Fe0 accepts it, although {probe.path} shows that it"
                                     f" rejects this shape")
        if m.mutation.expect == Expect.SAME_CODE and run.program().code != original.code:
            return Finding(run.path, f"Fe0 compiles it to other bytes than {original.path}")
        return Agreement.ACCEPTED
    if fe is not None:
        return Agreement.BOTH_REJECT
    error = run.error()
    if error is None:
        return Finding(run.path, f"Fe0 does not compile it cleanly: {run.said()}")
    if probe is not None:
        if error.code == probe.code:
            return Agreement.KNOWN_NARROWING
        return Finding(run.path, f"Fe accepts it and Fe0 rejects it with"
                                 f" {error.describe(m.source)}, not with {probe.code} as"
                                 f" {probe.path} does")
    if error.code in narrowings.known:
        return Agreement.KNOWN_NARROWING
    return Finding(run.path, f"Fe accepts it and Fe0 rejects it: {error.describe(m.source)}")


def originals(seeds: Iterable[Seed]) -> list[Original]:
    """Returns the corpus programs and the generated programs of `seeds`, each with Fe0's bytes.
    Errors with RuntimeError when Fe0 does not compile one."""
    named = [(p, FeSource(p.read_text())) for p in sorted(embed.CORPUS.glob("*.fe"))]
    named += [(GEN / program_file(s), Gen(s).program().program) for s in seeds]
    out = []
    for path, source in named:
        run = cli_check.Run.of(path.relative_to(ROOT), source)
        if not run.compiled():
            raise RuntimeError(f"Fe0 does not compile {run.path}: {run.said()}")
        out.append(Original(run.path, source, run.program().code))
    return out


def print_agreements(agreements: Counter[tuple[Agreement, Mutation]]) -> None:
    """Prints, for each agreement but ACCEPTED, how many mutants of each mutation it counted."""
    rows: list[tuple[str, Agreement, list[Mutation]]] = [
        ("both compilers reject", Agreement.BOTH_REJECT,
         [m for m in Mutation if not m.breaks_rule]),
        ("both compilers accept, so the rule was not broken", Agreement.MISSED,
         [m for m in Mutation if m.breaks_rule]),
        ("Fe accepts and Fe0 rejects with the probe's code", Agreement.KNOWN_NARROWING,
         [m for m in Mutation if m.expect == Expect.NARROWING]),
    ]
    for label, agreement, mutations in rows:
        print(f"{label}: " + ", ".join(f"{m} {agreements[agreement, m]}" for m in mutations))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=1, help="the first seed (default 1)")
    ap.add_argument("-n", type=int, default=10, help="the number of generated programs (default 10)")
    ap.add_argument("--per-program", type=int, default=2,
                    help="the number of mutants of each program (default 2)")
    args = ap.parse_args()
    cli_check.build()
    narrowings = Narrowings.load()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.fe"):
        old.unlink()
    findings: list[Finding] = []
    agreements: Counter[tuple[Agreement, Mutation]] = Counter()
    checked = 0
    first = Seed(args.seed)
    for original in originals(seeds_from(first, args.n)):
        rng = random.Random(f"{first}:{original.path.stem}")
        for i, m in enumerate(mutants(original.source, rng, args.per_program)):
            path = OUT / f"{original.path.stem}_{m.mutation}_{i}.fe"
            path.write_text(m.source)
            checked += 1
            run = cli_check.Run.of(path.relative_to(ROOT), m.source)
            match classify(m, original, run, embed.fe_rejection(run.path), narrowings):
                case Finding() as found:
                    print(found, flush=True)
                    findings.append(found)
                case Agreement() as agreement:
                    agreements[agreement, m.mutation] += 1
    print(f"{checked} mutants: {len(findings)} findings")
    print_agreements(agreements)
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
