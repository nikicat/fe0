"""Shared parts of the scripts that write Fe tests.

The differential tests that these scripts write call fe0/src/difftest.fe, and every generator
writes them through this module, so that all of them call it the same way.
"""
import bisect
import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import NamedTuple

# The fe binary when the environment variable FE is not set.
FE_DEFAULT = Path.home() / ".fe/bin/fe"
FE = os.environ.get("FE") or str(FE_DEFAULT)
ROOT = Path(__file__).resolve().parent.parent
FE0 = ROOT / "fe0"
MAX = (1 << 256) - 1
# Longer than the parser's MAX_DEPTH, so a chain of this many `else if` shows that the parser and
# the code generator read such a chain in a loop, not by recursion.
CHAIN_LEN = 40


def lit(s):
    """`s` as a Fe string literal."""
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def write_formatted(path, text):
    """Writes `text` to `path` and formats the file with `fe fmt`. Errors when `text` is not
    valid Fe, or when `fe fmt` fails."""
    path.write_text(text)
    result = subprocess.run([FE, "fmt", str(path)], check=True, capture_output=True, text=True)
    # `fe fmt` exits with 0 on a file that does not parse, and only warns on stderr.
    if result.stderr:
        raise RuntimeError(f"fe fmt {path}: {result.stderr.strip()}")


class Payload:
    """Bytes sent to a contract, together with a value in wei. It mirrors `difftest::Payload` in
    fe0/src/difftest.fe."""

    def __init__(self, value):
        self.value = value

    def build(self, var):
        """Returns the Fe statements that declare `var` as a `difftest::Payload` and fill it with
        the bytes."""
        wei = f"std::evm::wei({self.value})" if self.value else "Wei::zero()"
        new = f"var {var} = difftest::Payload::new({wei})"
        return [new] + [f"{var}.{c}" for c in self.pushes()]


def push_words(words, extra):
    """Returns the Payload method calls that append the ABI `words`, then `extra` bytes of 0x99."""
    return [f"push_word({w:#x})" for w in words] + ["push(0x99)"] * extra


class Deploy(Payload):
    """Constructor arguments: words, then `extra` bytes."""

    def __init__(self, *words, extra=0, value=0):
        super().__init__(value)
        self.words, self.extra = words, extra

    def pushes(self):
        return push_words(self.words, self.extra)


class Call(Payload):
    """Calldata: a 4-byte selector, words, then `extra` bytes. Errors when `sel` does not fit
    in 4 bytes."""

    def __init__(self, sel, *words, extra=0, value=0):
        # Fe cuts a literal that is too wide for its type without an error, so the u32 parameter
        # of `difftest::Payload.push_selector` would not catch it (docs/WORKAROUNDS.md).
        if sel not in range(1 << 32):
            raise ValueError(f"the selector {sel:#x} does not fit in 4 bytes")
        super().__init__(value)
        self.sel, self.words, self.extra = sel, words, extra

    def pushes(self):
        return [f"push_selector({self.sel:#x})"] + push_words(self.words, self.extra)


class RawCall(Payload):
    """Calldata given byte by byte."""

    def __init__(self, *data, value=0):
        super().__init__(value)
        self.data = data

    def pushes(self):
        return [f"push({b})" for b in self.data]


# A selector that DISPATCH sends as an unknown one.
PROBE_SELECTOR = 0x7777
# Calls that reach the dispatcher's empty reverts: no selector, a short one, and an unknown one.
DISPATCH = [RawCall(), RawCall(0, 0, 1), Call(PROBE_SELECTOR)]


def difftest_use(ingot):
    """Returns the line that imports the difftest module.

    `ingot` is the name under which the importing code knows the fe0 ingot.
    """
    return f"use {ingot}::difftest"


class Kind(Enum):
    """What the panic code of a failed differential test names.

    Each value is the first code of its range, in increasing order. Fe's own panic codes are
    below 0x100. The codes are a protocol with fe0/src/difftest.fe, which states TOO_LARGE and
    ACCEPTED and takes case codes as `CaseCode`. Change both sides together.
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
    # An error of Fe0: the code is its `DiagWord`.
    DIAG = 1 << 40

    def case_code(self, number):
        """Returns the Fe expression of the `difftest::CaseCode` for `number` in this range."""
        return f"difftest::CaseCode::new({self.value + number:#x})"


class Failure(NamedTuple):
    """The meaning of a panic code that a differential test failed with."""

    kind: Kind
    # The code less the start of its range: Fe's panic code, a Case's number (for CASE and SIZE),
    # the index of a call of DISPATCH from 1, 0 for ACCEPTED, or the diag word.
    number: int

    @classmethod
    def decode(cls, code):
        """Returns what the panic code `code` names."""
        kind = next(k for k in reversed(Kind) if k.value <= code)
        return cls(kind, code if kind is Kind.DIAG else code - kind.value)


class Case(NamedTuple):
    """A deployment or call of a differential test, with the number that its panic code holds."""

    number: int
    payload: Payload

    @property
    def code(self):
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
BALANCE = 1000
# The effects of a function that deploys and calls contracts.
USES_EVM = "uses (evm: mut Evm)"


def indent(lines):
    """Returns `lines` indented by one level of Fe code."""
    return ["    " + s for s in lines]


def evm_test(name, balance, statements):
    """Returns the lines of a test function `name` that runs `statements`, with `balance` wei to
    spend on the EVM."""
    return [f"#[test(balance = {balance})]", f"fn {name}() {USES_EVM} {{"] + indent(statements) + ["}"]


@dataclass(frozen=True)
class DiffTest:
    """A test that compares Fe0's build of a program with the official build.

    The test fails with the panic code (`Kind`) of the first case whose builds differ.
    """

    # The test function's name.
    test: str
    # The official build's contract, declared in the test's module.
    contract: str
    # The program as Fe0 compiles it.
    source: str
    # The deployments and calls that the test sends.
    cases: Cases

    @property
    def runner(self):
        """Returns the name of the function that sends the cases."""
        return f"run_{self.test}"

    def lines(self):
        """Returns the lines of the runner and of the test function."""
        out = ["", f"pub fn {self.runner}() {USES_EVM} {{",
               f"    let b = difftest::Builds {{ ours: difftest::ours({lit(self.source)}), theirs: "
               f"difftest::theirs({self.contract}::init_code_offset(), {self.contract}::init_code_len()) }}"]
        for d in self.cases.deploys:
            out += block(d.payload.build("a") + [f"let _ = b.deploy(a, {d.code})"])
        m = self.cases.main.payload
        out += indent(m.build("a"))
        out.append(f"    let p = b.deploy_main(a, {self.cases.main.code})")
        for c in self.cases.calls:
            out += call(c.payload, c.code)
        for k, c in enumerate(DISPATCH, start=1):
            out += call(c, Kind.PROBE.case_code(k))
        return out + ["}", ""] + evm_test(self.test, BALANCE, [f"{self.runner}()"])


def call(payload, case):
    """Returns the block of a runner that sends `payload` to the main deployment and
    fails with the case code `case`, a Fe expression, when the builds differ."""
    return block(payload.build("d") + [f"p.call(d, {case})"])


def reject_test(test, source, expected):
    """Returns the lines of a test function that checks that Fe0 rejects `source` with the
    DiagWord `expected`."""
    return ["", "#[test]", f"fn {test}() {{", f"    difftest::rejects({lit(source)}, difftest::DiagWord::new({expected.pack():#x}))", "}"]


def block(statements):
    """Returns `statements` as a braced block inside a runner."""
    return indent(["{"] + indent(statements) + ["}"])


# What ends a line, as fe0's Text.line_col counts lines: `\n`, `\r\n` or a lone `\r`.
LINE_END = r"\r\n?|\n"


def line_starts(data):
    """Returns the byte offset of each line of `data`, which ends lines at LINE_END."""
    return [0] + [m.end() for m in re.finditer(LINE_END.encode(), data)]


@dataclass(frozen=True)
class DiagWord:
    """An error of Fe0 as one panic code. `DiagWord` in fe0/src/difftest.fe packs the same
    layout, and its test `diag_word_layout` checks the example of `check_diag_word`."""

    # The phase letter, such as "E" in E116.
    letter: str
    # The number within the phase, such as 116 in E116.
    number: int
    # The byte offset where the error points.
    offset: int

    @classmethod
    def at(cls, letter, number, line, col, source):
        """Returns the error with `letter` and `number` at `line` and `col` of `source`, the
        inverse of `describe`.

        Errors when `line` is past the end of `source`.
        """
        starts = line_starts(source.encode())
        if line > len(starts):
            raise ValueError(f"line {line} is past the end")
        return cls(letter, number, starts[line - 1] + col - 1)

    @classmethod
    def unpack(cls, word):
        """Returns the error that the diag word `word` holds."""
        return cls(chr(word >> 40), word >> 24 & 0xffff, word & 0xffffff)

    def pack(self):
        """Returns the diag word, as `difftest::DiagWord::of` packs it."""
        return ord(self.letter) << 40 | self.number << 24 | self.offset

    def describe(self, source):
        """Returns the code, line and column of the error in `source`, such as `E116 12:9`."""
        starts = line_starts(source.encode())
        line = bisect.bisect_right(starts, self.offset)
        return f"{self.letter}{self.number:03} {line}:{self.offset - starts[line - 1] + 1}"


def check_diag_word():
    r"""Checks DiagWord against the example of `difftest::DiagWord` and one source with `\r`."""
    e116 = DiagWord("E", 116, 9)
    assert e116.pack() == 0x45_0074_000009 and DiagWord.unpack(e116.pack()) == e116
    assert Failure.decode(e116.pack()) == Failure(Kind.DIAG, e116.pack())
    source = "a\r\nx\ryz"
    assert DiagWord.at("E", 116, 3, 2, source) == DiagWord("E", 116, 6)
    assert DiagWord("E", 116, 6).describe(source) == "E116 3:2"
