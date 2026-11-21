"""Fe0 source text as tokens, one tokenizer for every tool that rewrites programs as text
(task Tdf1kp).

The tokens follow Fe0's lexer (SPEC.md §1) closely enough to find places in a program that the
lexer accepts. They do not check a program.
"""
import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from enum import StrEnum
from typing import NamedTuple, NewType

from fegen import LINE_END, ByteOffset, FeName


# An index into a list of tokens. It means nothing in another list, such as the significant
# tokens of the same program.
TokenIndex = NewType("TokenIndex", int)


class Kind(StrEnum):
    COMMENT = "comment"
    STRING = "string"
    NEWLINE = "newline"
    SPACE = "space"
    OPEN = "open"
    CLOSE = "close"
    WORD = "word"
    NUMBER = "number"
    OP = "op"
    # Any byte that starts no other token, so every byte of a program is in some token.
    OTHER = "other"

    @property
    def trivia(self) -> bool:
        """True if the token is white space or a comment. False for a line end, which can end a
        statement (SPEC.md §1)."""
        return self in (Kind.SPACE, Kind.COMMENT)


class Op(StrEnum):
    """The brackets, punctuation and operators of Fe0 (SPEC.md §1)."""

    LPAREN = "("
    RPAREN = ")"
    LBRACE = "{"
    RBRACE = "}"
    LBRACKET = "["
    RBRACKET = "]"
    COLON = ":"
    # Fe0 reads two `:`, but Fe reads one token and rejects `: :` (SPEC.md §1), so no tool
    # puts a space inside it.
    PATH = "::"
    COMMA = ","
    DOT = "."
    HASH = "#"
    ARROW = "->"
    PLUS = "+"
    MINUS = "-"
    STAR = "*"
    SLASH = "/"
    PERCENT = "%"
    TILDE = "~"
    BANG = "!"
    CARET = "^"
    AMP = "&"
    PIPE = "|"
    ANDAND = "&&"
    OROR = "||"
    LT = "<"
    GT = ">"
    ASSIGN = "="
    EQ = "=="
    NE = "!="
    LE = "<="
    GE = ">="
    SHL = "<<"
    SHR = ">>"
    PLUS_ASSIGN = "+="
    MINUS_ASSIGN = "-="
    STAR_ASSIGN = "*="
    SLASH_ASSIGN = "/="
    PERCENT_ASSIGN = "%="
    AMP_ASSIGN = "&="
    PIPE_ASSIGN = "|="
    CARET_ASSIGN = "^="
    SHL_ASSIGN = "<<="
    SHR_ASSIGN = ">>="


OPENERS: frozenset[Op] = frozenset({Op.LPAREN, Op.LBRACE, Op.LBRACKET})
CLOSERS: frozenset[Op] = frozenset({Op.RPAREN, Op.RBRACE, Op.RBRACKET})
ASSIGN_OPS: frozenset[Op] = frozenset({
    Op.ASSIGN, Op.PLUS_ASSIGN, Op.MINUS_ASSIGN, Op.STAR_ASSIGN, Op.SLASH_ASSIGN,
    Op.PERCENT_ASSIGN, Op.AMP_ASSIGN, Op.PIPE_ASSIGN, Op.CARET_ASSIGN, Op.SHL_ASSIGN,
    Op.SHR_ASSIGN})


class Keyword(StrEnum):
    """The words that the tools look for: some of Fe0's keywords, and `init`, a contextual word
    that may also name something (SPEC.md §1)."""

    LET = "let"
    IF = "if"
    WHILE = "while"
    CONTRACT = "contract"
    STRUCT = "struct"
    VAR = "var"
    CONST = "const"
    MUT = "mut"
    FN = "fn"
    MSG = "msg"
    INIT = "init"
    RETURN = "return"
    USES = "uses"
    TRUE = "true"
    FALSE = "false"


def _alternation(ops: Iterable[Op]) -> bytes:
    """Returns a regex that matches any of `ops`, the longest first, as `Lexer.op_or_assign` in
    fe0/src/lexer.fe reads an operator."""
    return b"|".join(re.escape(o.encode()) for o in sorted(ops, key=len, reverse=True))


_TOKEN = re.compile(rb'(?P<comment>//[^\r\n]*)|(?P<string>"(?:[^"\\\r\n]|\\.)*")'
                    rb"|(?P<newline>" + LINE_END.encode() + rb")|(?P<space>[ \t]+)"
                    rb"|(?P<open>" + _alternation(OPENERS) + rb")"
                    rb"|(?P<close>" + _alternation(CLOSERS) + rb")"
                    rb"|(?P<word>[A-Za-z_][A-Za-z0-9_]*)|(?P<number>[0-9][0-9A-Za-z_]*)"
                    rb"|(?P<op>" + _alternation(set(Op) - OPENERS - CLOSERS) + rb")"
                    rb"|(?P<other>.)", re.S)
assert set(Kind) == set(_TOKEN.groupindex)

_SYMBOLS: dict[bytes, Op | Keyword] = {s.encode(): s for s in [*Op, *Keyword]}


class Token(NamedTuple):
    kind: Kind
    start: ByteOffset
    end: ByteOffset
    text: bytes

    @property
    def symbol(self) -> Op | Keyword | None:
        """The token as an operator, bracket or keyword. None for any other token."""
        return _SYMBOLS.get(self.text)

    @property
    def word(self) -> FeName | None:
        """The word, a keyword or not. None for a token that is not a word."""
        return FeName(self.text.decode()) if self.kind == Kind.WORD else None


def tokens(data: bytes) -> Iterator[Token]:
    """Yields every token of `data` in order, white space and comments included, unlike
    `significant`."""
    for m in _TOKEN.finditer(data):
        assert m.lastgroup is not None
        yield Token(Kind(m.lastgroup), ByteOffset(m.start()), ByteOffset(m.end()), m[0])


def next_index(toks: Sequence[Token], after: TokenIndex,
               p: Callable[[Token], bool]) -> TokenIndex | None:
    """Returns the index of the first token after `toks[after]` that `p` accepts. Returns None
    when `p` accepts no later token."""
    return next((TokenIndex(k) for k in range(after + 1, len(toks)) if p(toks[k])), None)


def significant(toks: Iterable[Token]) -> list[Token]:
    """Returns the tokens that are not trivia (`Kind.trivia`), in order."""
    return [t for t in toks if not t.kind.trivia]


class BracketPair(NamedTuple):
    open: TokenIndex
    close: TokenIndex


class Brackets:
    """The bracket pairs of a list of tokens."""

    def __init__(self, toks: Sequence[Token]) -> None:
        self.toks = toks
        # The closing bracket of each open bracket that is closed, by the open bracket.
        self._close: dict[TokenIndex, TokenIndex] = {}
        stack: list[TokenIndex] = []
        for i, t in enumerate(toks):
            if t.kind == Kind.OPEN:
                stack.append(TokenIndex(i))
            elif t.kind == Kind.CLOSE and stack:
                self._close[stack.pop()] = TokenIndex(i)

    def __iter__(self) -> Iterator[BracketPair]:
        """Yields each pair, in the order the pairs close."""
        return (BracketPair(o, c) for o, c in self._close.items())

    def close(self, o: TokenIndex) -> TokenIndex | None:
        """Returns the index of the bracket that closes the one at `o`. Returns None when `o` is
        not an open bracket that is closed."""
        return self._close.get(o)

    def top_level(self, pair: BracketPair) -> Iterator[Token]:
        """Yields, in order, the tokens inside `pair`, leaving out each inner bracket pair and
        the tokens it holds."""
        i = pair.open + 1
        while i < pair.close:
            if (c := self._close.get(TokenIndex(i))) is not None:
                i = c + 1
            else:
                yield self.toks[i]
                i += 1
