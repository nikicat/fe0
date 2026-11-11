"""Shared parts of the scripts that write Fe tests.

The differential tests that these scripts write call fe0/src/difftest.fe, and every generator
writes them through this module, so that all of them call it the same way.
"""
import bisect
import os
import re
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import NamedTuple, NewType, Self

# The text of a Fe program or module.
FeSource = NewType("FeSource", str)
# One line of Fe code, without its line end.
FeLine = NewType("FeLine", str)
# A Fe expression, such as a string literal or a `difftest::CaseCode`.
FeExpr = NewType("FeExpr", str)
# A Fe identifier that names a contract, a function or a local.
FeName = NewType("FeName", str)
# The name of a Fe test function, as `fe test` reports it.
TestName = NewType("TestName", str)
# A call of a `difftest::Payload` method that appends bytes, without its receiver, such as
# `push(0x99)`.
Push = NewType("Push", str)
# An amount of wei.
Wei = NewType("Wei", int)
# The 4-byte selector of a msg variant.
Selector = NewType("Selector", int)
# A 256-bit ABI word.
Word = NewType("Word", int)
# The code of a Panic that a test fails with (`Kind` says what it names).
PanicCode = NewType("PanicCode", int)
# A byte offset into a FeSource.
ByteOffset = NewType("ByteOffset", int)
# The letter of a phase of Fe0, such as "E" for effects.
PhaseLetter = NewType("PhaseLetter", str)

# The fe binary when the environment variable FE is not set.
FE_DEFAULT: Path = Path.home() / ".fe/bin/fe"
FE: str = os.environ.get("FE") or str(FE_DEFAULT)
ROOT: Path = Path(__file__).resolve().parent.parent
FE0: Path = ROOT / "fe0"
MAX: Word = Word((1 << 256) - 1)
# Longer than the parser's MAX_DEPTH, so a chain of this many `else if` shows that the parser and
# the code generator read such a chain in a loop, not by recursion.
CHAIN_LEN = 40


def source(lines: Iterable[FeLine]) -> FeSource:
    """Returns the text of `lines`, with a line end after each."""
    return FeSource("".join(s + "\n" for s in lines))


def lit(s: str) -> FeExpr:
    """`s` as a Fe string literal."""
    return FeExpr('"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"')


def write_formatted(path: Path, text: FeSource) -> None:
    """Writes `text` to `path` and formats the file with `fe fmt`. Errors when `text` is not
    valid Fe, or when `fe fmt` fails."""
    path.write_text(text)
    result = subprocess.run([FE, "fmt", str(path)], check=True, capture_output=True, text=True)
    # `fe fmt` exits with 0 on a file that does not parse, and only warns on stderr.
    if result.stderr:
        raise RuntimeError(f"fe fmt {path}: {result.stderr.strip()}")


class Payload(ABC):
    """Bytes sent to a contract, together with a value in wei. It mirrors `difftest::Payload` in
    fe0/src/difftest.fe."""

    def __init__(self, value: Wei) -> None:
        self.value = value

    @abstractmethod
    def pushes(self) -> list[Push]:
        """Returns the method calls that append the bytes."""

    def build(self, var: FeName) -> list[FeLine]:
        """Returns the Fe statements that declare `var` as a `difftest::Payload` and fill it with
        the bytes."""
        wei = f"std::evm::wei({self.value})" if self.value else "Wei::zero()"
        new = FeLine(f"var {var} = difftest::Payload::new({wei})")
        return [new] + [FeLine(f"{var}.{c}") for c in self.pushes()]


def push_words(words: Sequence[Word], extra: int) -> list[Push]:
    """Returns the Payload method calls that append the ABI `words`, then `extra` bytes of 0x99."""
    return [Push(f"push_word({w:#x})") for w in words] + [Push("push(0x99)")] * extra


class Deploy(Payload):
    """Constructor arguments: words, then `extra` bytes."""

    def __init__(self, *words: Word, extra: int = 0, value: Wei = Wei(0)) -> None:
        super().__init__(value)
        self.words, self.extra = words, extra

    def pushes(self) -> list[Push]:
        return push_words(self.words, self.extra)


class Call(Payload):
    """Calldata: a 4-byte selector, words, then `extra` bytes. Errors when `sel` does not fit
    in 4 bytes."""

    def __init__(self, sel: Selector, *words: Word, extra: int = 0, value: Wei = Wei(0)) -> None:
        # Fe cuts a literal that is too wide for its type without an error, so the u32 parameter
        # of `difftest::Payload.push_selector` would not catch it (docs/WORKAROUNDS.md).
        if sel not in range(1 << 32):
            raise ValueError(f"the selector {sel:#x} does not fit in 4 bytes")
        super().__init__(value)
        self.sel, self.words, self.extra = sel, words, extra

    def pushes(self) -> list[Push]:
        return [Push(f"push_selector({self.sel:#x})")] + push_words(self.words, self.extra)


class RawCall(Payload):
    """Calldata given byte by byte."""

    def __init__(self, *data: int, value: Wei = Wei(0)) -> None:
        super().__init__(value)
        self.data = data

    def pushes(self) -> list[Push]:
        return [Push(f"push({b})") for b in self.data]


# A selector that DISPATCH sends as an unknown one.
PROBE_SELECTOR: Selector = Selector(0x7777)
# Calls that reach the dispatcher's empty reverts: no selector, a short one, and an unknown one.
DISPATCH: list[Payload] = [RawCall(), RawCall(0, 0, 1), Call(PROBE_SELECTOR)]


def difftest_use(ingot: str) -> FeLine:
    """Returns the line that imports the difftest module.

    `ingot` is the name under which the importing code knows the fe0 ingot.
    """
    return FeLine(f"use {ingot}::difftest")


class Kind(Enum):
    """What the panic code of a failed differential test names.

    Each value is the first code of its range, in increasing order. Fe's own panic codes are
    below 0x100. The codes are a protocol with the panic-code constants of fe0/src/difftest.fe,
    which takes case codes as `CaseCode`. Change both sides together.
    """

    # A panic of the test itself, such as Panic(0x11) for an overflow.
    PANIC = 0
    # A deployment or call: the code is this value plus its `Case.number`.
    CASE = 1 << 32
    # A call of DISPATCH: the code is this value plus its index there, from 1.
    PROBE = 2 << 32
    # A deployment whose Fe0 code is larger than a chain accepts. The code is its CASE code
    # plus difftest's TOO_LARGE, which is SIZE less CASE.
    SIZE = 3 << 32
    # A reject program that Fe0 accepts. The code is difftest's ACCEPTED.
    ACCEPTED = 4 << 32
    # A program whose code from the native CLI differs from Fe0's on the EVM. difftest's
    # `same_code` says what the code holds.
    CODE_DIFFERS = 5 << 32
    # An error of Fe0: the code is its `DiagWord`.
    DIAG = 1 << 40

    def case_code(self, number: int) -> FeExpr:
        """Returns the Fe expression of the `difftest::CaseCode` for `number` in this range."""
        return FeExpr(f"difftest::CaseCode::new({self.value + number:#x})")


class Failure(NamedTuple):
    """The meaning of a panic code that a differential test failed with."""

    kind: Kind
    # The code less the start of its range, which each Kind's comment describes. For DIAG, it is
    # the whole diag word.
    number: int

    @classmethod
    def decode(cls, code: PanicCode) -> Self:
        """Returns what the panic code `code` names."""
        kind = next(k for k in reversed(Kind) if k.value <= code)
        return cls(kind, code if kind is Kind.DIAG else code - kind.value)


class Case(NamedTuple):
    """A deployment or call of a differential test, with the number that its panic code holds."""

    number: int
    payload: Payload

    @property
    def code(self) -> FeExpr:
        """Returns the Fe expression of this case's `difftest::CaseCode`."""
        return Kind.CASE.case_code(self.number)


class Cases(NamedTuple):
    """What a differential test sends. Every test also sends the calls of DISPATCH."""

    # The deployment that gets the calls. It must create a contract.
    main: Case
    # Other deployments, checked only for whether they create a contract.
    deploys: Sequence[Case]
    # The calls sent to the main deployment, before those of DISPATCH.
    calls: Sequence[Case]


# The wei that the test of one program spends at most on its deployments and calls.
BALANCE: Wei = Wei(1000)
# The effects of a function that deploys and calls contracts.
USES_EVM = "uses (evm: mut Evm)"


def indent(lines: list[FeLine]) -> list[FeLine]:
    """Returns `lines` indented by one level of Fe code."""
    return [FeLine("    " + s) for s in lines]


def evm_test(name: TestName, balance: Wei, statements: list[FeLine]) -> list[FeLine]:
    """Returns the lines of a test function `name` that runs `statements`, with `balance` wei to
    spend on the EVM."""
    head = [FeLine(f"#[test(balance = {balance})]"), FeLine(f"fn {name}() {USES_EVM} {{")]
    return head + indent(statements) + [FeLine("}")]


@dataclass(frozen=True)
class DiffTest:
    """A test that compares Fe0's build of a program with the official build.

    The test fails with the panic code (`Kind`) of the first case whose builds differ.
    """

    # The test function's name.
    test: TestName
    # The official build's contract, declared in the test's module.
    contract: FeName
    # The program as Fe0 compiles it.
    source: FeSource
    # The deployments and calls that the test sends.
    cases: Cases

    @property
    def runner(self) -> FeName:
        """Returns the name of the function that sends the cases."""
        return FeName(f"run_{self.test}")

    def lines(self) -> list[FeLine]:
        """Returns the lines of the runner and of the test function."""
        theirs = (f"difftest::theirs({self.contract}::init_code_offset(),"
                  f" {self.contract}::init_code_len())")
        ours = f"difftest::ours({lit(self.source)})"
        out = [FeLine(""), FeLine(f"pub fn {self.runner}() {USES_EVM} {{"),
               FeLine(f"    let b = difftest::Builds {{ ours: {ours}, theirs: {theirs} }}")]
        a = FeName("a")
        for d in self.cases.deploys:
            out += block(d.payload.build(a) + [FeLine(f"let _ = b.deploy({a}, {d.code})")])
        m = self.cases.main.payload
        out += indent(m.build(a))
        out.append(FeLine(f"    let p = b.deploy_main({a}, {self.cases.main.code})"))
        for c in self.cases.calls:
            out += call(c.payload, c.code)
        for k, probe in enumerate(DISPATCH, start=1):
            out += call(probe, Kind.PROBE.case_code(k))
        test = evm_test(self.test, BALANCE, [FeLine(f"{self.runner}()")])
        return out + [FeLine("}"), FeLine("")] + test


def call(payload: Payload, case: FeExpr) -> list[FeLine]:
    """Returns the block of a runner that sends `payload` to the main deployment and
    fails with the case code `case`, a Fe expression, when the builds differ."""
    d = FeName("d")
    return block(payload.build(d) + [FeLine(f"p.call({d}, {case})")])


def reject_test(test: TestName, source: FeSource, expected: "DiagWord") -> list[FeLine]:
    """Returns the lines of a test function that checks that Fe0 rejects `source` with the
    DiagWord `expected`."""
    check = f"difftest::rejects({lit(source)}, difftest::DiagWord::new({expected.pack():#x}))"
    return [FeLine(""), FeLine("#[test]"), FeLine(f"fn {test}() {{"), FeLine(f"    {check}"),
            FeLine("}")]


def block(statements: list[FeLine]) -> list[FeLine]:
    """Returns `statements` as a braced block inside a runner."""
    return indent([FeLine("{")] + indent(statements) + [FeLine("}")])


# What ends a line, as fe0's Text.line_col counts lines: `\n`, `\r\n` or a lone `\r`.
LINE_END = r"\r\n?|\n"


def line_starts(data: bytes) -> list[ByteOffset]:
    """Returns the byte offset of each line of `data`, which ends lines at LINE_END."""
    return [ByteOffset(0)] + [ByteOffset(m.end()) for m in re.finditer(LINE_END.encode(), data)]


# The code of an error, such as `E116`, as the CLI prints it and a reject header names it.
CODE = r"(?P<letter>[A-Z])(?P<number>\d{3})"
# The line and column of an error, such as `12:9`. Both count from 1.
POS = r"(?P<line>\d+):(?P<col>\d+)"


class LineCol(NamedTuple):
    """A position in a source, as fe0's `LineCol` in fe0/src/lexer.fe holds it."""

    line: int
    col: int

    @classmethod
    def matched(cls, m: re.Match[str]) -> Self:
        """Returns the position that the match `m` names. The pattern of `m` holds the groups of
        POS."""
        return cls(int(m["line"]), int(m["col"]))

    @classmethod
    def of(cls, offset: ByteOffset, source: FeSource) -> Self:
        """Returns the position of the byte offset `offset` in `source`."""
        starts = line_starts(source.encode())
        line = bisect.bisect_right(starts, offset)
        return cls(line, offset - starts[line - 1] + 1)

    def offset(self, source: FeSource) -> ByteOffset:
        """Returns the byte offset of the position in `source`, the inverse of `of`.

        Errors when the line is past the end of `source`.
        """
        starts = line_starts(source.encode())
        if self.line > len(starts):
            raise ValueError(f"line {self.line} is past the end")
        return ByteOffset(starts[self.line - 1] + self.col - 1)

    def __str__(self) -> str:
        """Returns the position as POS spells it, such as `12:9`."""
        return f"{self.line}:{self.col}"


class DiagCode(NamedTuple):
    """The kind of an error of Fe0, apart from where it points."""

    # The phase letter, such as "E" in E116.
    letter: PhaseLetter
    # The number within the phase, such as 116 in E116.
    number: int

    @classmethod
    def matched(cls, m: re.Match[str]) -> Self:
        """Returns the code that the match `m` names. The pattern of `m` holds the groups of
        CODE."""
        return cls(PhaseLetter(m["letter"]), int(m["number"]))

    def __str__(self) -> str:
        """Returns the code as CODE spells it, such as `E116`."""
        return f"{self.letter}{self.number:03}"


@dataclass(frozen=True)
class DiagWord:
    """An error of Fe0 as one panic code. `DiagWord` in fe0/src/difftest.fe packs the same
    layout, and its test `diag_word_layout` checks the example of `check_diag_word`."""

    code: DiagCode
    # Where the error points.
    offset: ByteOffset

    @classmethod
    def matched(cls, m: re.Match[str], source: FeSource) -> Self:
        """Returns the error that the match `m` names in `source`. The pattern of `m` holds the
        groups of CODE and POS.

        Errors as `LineCol.offset` does.
        """
        return cls(DiagCode.matched(m), LineCol.matched(m).offset(source))

    @classmethod
    def unpack(cls, word: PanicCode) -> Self:
        """Returns the error that the diag word `word` holds."""
        code = DiagCode(PhaseLetter(chr(word >> 40)), word >> 24 & 0xffff)
        return cls(code, ByteOffset(word & 0xffffff))

    def pack(self) -> PanicCode:
        """Returns the diag word, as `difftest::DiagWord::of` packs it."""
        return PanicCode(ord(self.code.letter) << 40 | self.code.number << 24 | self.offset)

    def describe(self, source: FeSource) -> str:
        """Returns the code, line and column of the error in `source`, such as `E116 12:9`."""
        return f"{self.code} {LineCol.of(self.offset, source)}"


def check_diag_word() -> None:
    r"""Checks DiagWord against the example of `difftest::DiagWord` and one source with `\r`."""
    e116 = DiagCode(PhaseLetter("E"), 116)
    assert str(e116) == "E116"
    at9 = DiagWord(e116, ByteOffset(9))
    assert at9.pack() == 0x45_0074_000009 and DiagWord.unpack(at9.pack()) == at9
    assert Failure.decode(at9.pack()) == Failure(Kind.DIAG, at9.pack())
    source = FeSource("a\r\nx\ryz")
    assert LineCol(3, 2).offset(source) == 6 and LineCol.of(ByteOffset(6), source) == LineCol(3, 2)
    assert DiagWord(e116, ByteOffset(6)).describe(source) == "E116 3:2"
