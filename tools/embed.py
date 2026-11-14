#!/usr/bin/env python3
"""Run the corpus through the differential harness of DESIGN.md §10.

It is also the library behind tools/gen.py, for call scripts and the harness.

Each program `corpus/X.fe` comes with a call script `corpus/X.calls`, which lists what the test
of the program deploys and sends. A call script has one entry per line, and `#` starts a comment:

    init 5 true            the main deployment, with these constructor arguments
    deploy 5 2             another deployment, checked only for whether it creates a contract
    Set 5                  a call to the variant `Set`, with argument words
    0x2a 1 2               a call by selector
    raw 0000002a01         calldata given as hex bytes

An argument is an integer, `MAX` (2**256 - 1), `true` or `false`, or such values combined with
parentheses and the operators + - * // ** << >> & | ^. It is written without spaces, as in
`2**255` or `MAX-1`, and its value must fit in 256 bits. An argument may also be `accountN`, which
names the address of node account N (fegen.Account). Any entry but `raw` may end with
`value=N`, the wei sent with it, `extra=N`, a number of bytes appended after the words, and
`from=N`, the node account that sends it. `from` applies only on a node (tools/node.py), as
DESIGN.md §10, "On a node", says.
Without an `init` line, the main deployment has no arguments. Every program also gets the calls
of `fegen.DISPATCH`.

Each reject program `corpus/reject/X.fe` names the error that Fe0 must give, in a header line:

    // expect: E116 12:9

The header gives the error code, then the line and column where the error points. Both count
from 1, and the column counts bytes. Another header line, `// fe: accepts`, marks a rule that
Fe0 adds on top of Fe, so the official compiler must accept the program (SPEC.md §8).

With --no-run, fe check still runs on every program.
"""
import argparse
import ast
import itertools
import operator
import os
import re
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum, StrEnum
from pathlib import Path
from typing import ClassVar, Never, NamedTuple, NewType, Protocol, Self

import fegen
from fegen import (MAX, ROOT, Account, AccountIndex, Arg, ByteOffset, Call, Case, Cases, Deploy,
                   DiagCode, DiagWord, DiffTest, ExtraBytes, Failure, FeLine, FeName, FeSource,
                   Kind, LineCol, PanicCode, Payload, PhaseLetter, RawCall, Selector, TestName, Wei,
                   Word)

CORPUS: Path = ROOT / "corpus"
REJECTS: Path = CORPUS / "reject"
OUT: Path = ROOT / "out/difftest"
# Programs per batch ingot (ADR 0003, Measurements).
BATCH = 25
# The start of the name of each batch ingot's test, which runs every program of the batch
# (DESIGN.md §10).
BATCH_TEST = "every_program_in_"


class ScriptError(Exception):
    pass


# A message that says what failed and where, one of those that the harness exits with.
FailureMessage = NewType("FailureMessage", str)
# An optimization level of `fe test`, such as "1".
OptLevel = NewType("OptLevel", str)


# Integer expressions in call scripts.
OPS: dict[type[ast.operator], Callable[[int, int], int]] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Pow: operator.pow,
    ast.LShift: operator.lshift, ast.RShift: operator.rshift, ast.FloorDiv: operator.floordiv,
    ast.BitOr: operator.or_, ast.BitAnd: operator.and_, ast.BitXor: operator.xor}
_MAX_WORD = "MAX"
NAMES: dict[str, Word] = {_MAX_WORD: MAX, "true": Word(1), "false": Word(0)}
# The start of an argument that names a node account by index, as in `account1`.
_ACCOUNT = "account"


def word(text: str) -> Word:
    """Returns the word that the argument `text` gives.

    Errors when `text` is not an integer expression of the call-script form, or when its value
    does not fit in 256 bits.
    """
    def ev(n: ast.expr) -> int:
        if isinstance(n, ast.Constant) and type(n.value) is int:
            return n.value
        if isinstance(n, ast.Name) and n.id in NAMES:
            return NAMES[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.left), ev(n.right))
        raise ValueError(n)
    try:
        v = ev(ast.parse(text, mode="eval").body)
        if type(v) is not int or not 0 <= v <= MAX:
            raise ValueError(v)
    except (SyntaxError, ArithmeticError, ValueError):
        raise ScriptError(f"Errors when reading the argument {text!r}: "
                          "it is not an integer expression whose value fits in 256 bits") from None
    return Word(v)


def arg(text: str) -> Arg:
    """Returns the argument that `text` gives: an account by index, or a word.

    Errors as `word` does when `text` names no account.
    """
    if m := re.fullmatch(rf"{_ACCOUNT}(\d+)", text):
        return Account(AccountIndex(int(m[1])))
    return word(text)


# A Fe0 line comment, as Lexer.skip_trivia reads it (SPEC §1).
LINE_COMMENT = re.compile(r"//[^\r\n]*")


def selectors(source: FeSource) -> dict[FeName, Selector]:
    """Returns the selector of each msg variant in `source`, by variant name."""
    return {FeName(name): Selector(int(sel, 0))
            for sel, name in re.findall(r"#\[selector\s*=\s*(\w+)\]\s*(\w+)",
                                        LINE_COMMENT.sub("", source))}


class Head(Enum):
    """A keyword that starts a call-script entry."""

    INIT = "init"
    DEPLOY = "deploy"
    RAW = "raw"


class ScriptOption(StrEnum):
    """An option that may end a call-script entry, written as `option=N`."""

    # The wei sent with the entry.
    VALUE = "value"
    # The number of bytes appended after the words.
    EXTRA = "extra"
    # The node account that sends the entry (fegen.AccountIndex).
    FROM = "from"


class Args(NamedTuple):
    """The argument words and options of an entry other than `raw`."""

    words: tuple[Arg, ...] = ()
    value: Wei = Wei(0)
    extra: ExtraBytes = ExtraBytes(0)
    sender: AccountIndex = AccountIndex(0)

    def render(self) -> list[str]:
        """The tokens of the words and of each option that is not 0."""
        opts = {ScriptOption.VALUE: self.value, ScriptOption.EXTRA: self.extra,
                ScriptOption.FROM: self.sender}
        return [*map(_render_arg, self.words),
                *(f"{o}={_render_word(v)}" for o, v in opts.items() if v)]

    @classmethod
    def parse(cls, tokens: Sequence[str]) -> Self:
        """Returns the arguments that `tokens` give.

        Errors when a token is not an argument of the call-script form.
        """
        args = list(tokens)
        opts: dict[ScriptOption, Word] = {}
        while args and (m := re.fullmatch(rf"({'|'.join(ScriptOption)})=(.*)", args[-1])):
            args.pop()
            opts[ScriptOption(m[1])] = word(m[2])
        return cls(tuple(map(arg, args)), Wei(opts.get(ScriptOption.VALUE, 0)),
                   ExtraBytes(opts.get(ScriptOption.EXTRA, 0)),
                   AccountIndex(opts.get(ScriptOption.FROM, 0)))

    def deploy(self) -> Deploy:
        """Returns a deployment with these constructor arguments."""
        return Deploy(*self.words, value=self.value, extra=self.extra)

    def call(self, sel: Selector) -> Call:
        """Returns a call of the selector `sel` with these arguments."""
        return Call(sel, *self.words, value=self.value, extra=self.extra)


class ScriptLine(ABC):
    """One entry of a call script."""

    @abstractmethod
    def render(self) -> str:
        """The text of the entry, without a line end."""

    @abstractmethod
    def payload(self, sels: Mapping[FeName, Selector]) -> Payload:
        """Returns what the entry sends, with `sels` as the selectors by variant name.

        Errors when the entry names a variant that `sels` lacks.
        """

    def sender(self) -> AccountIndex:
        """Returns the account that sends the entry."""
        return AccountIndex(0)

    def case(self, number: int, sels: Mapping[FeName, Selector]) -> Case:
        """Returns the entry as the case `number`, with `sels` as the selectors by variant name.

        Errors as payload does.
        """
        return Case(number, self.payload(sels), self.sender())

    @staticmethod
    def parse(text: str) -> "ScriptLine | None":
        """Returns the entry that the line `text` gives, or None for a blank or comment line.

        Errors when the line is not of the call-script form.
        """
        tokens = text.split("#", 1)[0].split()
        if not tokens:
            return None
        first, args = tokens[0], tokens[1:]
        if first == Head.RAW.value:
            if len(args) > 1 or not re.fullmatch(r"([0-9a-fA-F]{2})*", "".join(args)):
                raise ScriptError(f"{Head.RAW.value} takes one string of hex bytes")
            return RawLine(bytes.fromhex("".join(args)))
        if first == Head.INIT.value:
            return InitLine(Args.parse(args))
        if first == Head.DEPLOY.value:
            return DeployLine(Args.parse(args))
        if re.fullmatch(r"0x[0-9a-fA-F]+|[0-9]+", first):
            return SelectorCallLine(Selector(int(first, 0)), Args.parse(args))
        return NamedCallLine(FeName(first), Args.parse(args))


class ArgsLine(ScriptLine):
    """An entry that takes arguments, among them its sender."""

    args: Args

    def sender(self) -> AccountIndex:
        return self.args.sender


@dataclass(frozen=True)
class DeploymentLine(ArgsLine):
    """An entry that deploys the program, with its arguments as constructor arguments."""

    # The keyword that starts the entry.
    keyword: ClassVar[Head]
    args: Args = Args()

    def render(self) -> str:
        return " ".join([self.keyword.value, *self.args.render()])

    def payload(self, sels: Mapping[FeName, Selector]) -> Payload:
        return self.args.deploy()


class InitLine(DeploymentLine):
    """An `init` entry: the main deployment."""

    keyword = Head.INIT


class DeployLine(DeploymentLine):
    """A `deploy` entry. It deploys the program once more, beside the main deployment."""

    keyword = Head.DEPLOY


@dataclass(frozen=True)
class NamedCallLine(ArgsLine):
    """A call to a msg variant by its name."""

    name: FeName
    args: Args = Args()

    def render(self) -> str:
        return " ".join([self.name, *self.args.render()])

    def payload(self, sels: Mapping[FeName, Selector]) -> Payload:
        if self.name not in sels:
            raise ScriptError(f"{self.name} is no variant of the program")
        return self.args.call(sels[self.name])


@dataclass(frozen=True)
class SelectorCallLine(ArgsLine):
    """A call by selector."""

    sel: Selector
    args: Args = Args()

    def render(self) -> str:
        return " ".join([f"{self.sel:#x}", *self.args.render()])

    def payload(self, sels: Mapping[FeName, Selector]) -> Payload:
        return self.args.call(self.sel)


@dataclass(frozen=True)
class RawLine(ScriptLine):
    """A `raw` entry: calldata given as bytes."""

    data: bytes

    def render(self) -> str:
        return f"{Head.RAW.value} {self.data.hex()}"

    def payload(self, sels: Mapping[FeName, Selector]) -> Payload:
        return RawCall(*self.data)


def _render_word(w: int) -> str:
    """The argument text of the word `w`: MAX by name, large words in hex, others in decimal."""
    if w == MAX:
        return _MAX_WORD
    return f"{w:#x}" if w >= 2**64 else str(w)


def _render_arg(a: Arg) -> str:
    """The argument text of `a`: an account by index, a word as _render_word gives it."""
    return f"{_ACCOUNT}{a.index}" if isinstance(a, Account) else _render_word(a)


def check_script_line() -> None:
    """Checks that rendered call-script entries parse back to the same entries."""
    for line in [InitLine(Args((Word(5), Word(1)))),
                 DeployLine(Args((Word(2),), value=Wei(7), extra=ExtraBytes(3))),
                 NamedCallLine(FeName("Set"), Args((MAX, Word(2**200)), extra=ExtraBytes(1),
                                                   sender=AccountIndex(2))),
                 NamedCallLine(FeName("Give"), Args((Account(AccountIndex(1)), Word(3)))),
                 SelectorCallLine(Selector(0x2a)), RawLine(bytes([0, 0x2a])), RawLine(b"")]:
        assert ScriptLine.parse(line.render()) == line, line


def parse_calls(path: Path, sels: Mapping[FeName, Selector]) -> Cases:
    """Returns what the call script `path` sends, with `sels` as the selectors by variant name.

    Each case's number is its line in the script. Without an `init` line, the main deployment is
    Case(0, Deploy()).
    """
    main = Case(0, Deploy())
    deploys: list[Case] = []
    calls: list[Case] = []
    for n, text in enumerate(path.read_text().splitlines(), start=1):
        try:
            line = ScriptLine.parse(text)
            if line is None:
                continue
            case = line.case(n, sels)
            match line:
                case InitLine() if main.number:
                    raise ScriptError(f"a second {Head.INIT.value} line")
                case InitLine():
                    main = case
                case DeployLine():
                    deploys.append(case)
                case _:
                    calls.append(case)
        except ScriptError as e:
            raise ScriptError(f"{path.relative_to(ROOT)}:{n}: {e}") from None
    return Cases(main, deploys, calls)


# The declaration of a contract, whose name is group 1.
CONTRACT = re.compile(r"^\s*(?:pub\s+)?contract\s+(\w+)", re.M)


def calls_path(program: Path) -> Path:
    """Returns the path of the call script that lies beside the program at `program`."""
    return program.with_suffix(".calls")


class Tested(Protocol):
    """A program with a test, whose failures `report` explains."""

    # The program, relative to ROOT.
    path: Path

    @property
    def test(self) -> TestName:
        """The name of the program's test."""
        ...

    def explain(self, code: PanicCode) -> FailureMessage | None:
        """Returns what the failure Panic(`code`) of the program's test means, or None for a code
        that it does not explain. `report` then gives the code itself."""
        ...


class BatchProgram(Tested, Protocol):
    """A program whose test runs in a batch ingot, which `Batch` writes."""

    @property
    def runner(self) -> FeName:
        """The name of the function that the batch test calls."""
        ...

    def module_text(self) -> FeSource:
        """Returns the module of the batch ingot that holds the program and its test."""
        ...


@dataclass
class Program:
    """A program with a call script, and the test that embed.py writes for it."""

    # The program, such as corpus/X.fe or corpus/gen/sN.fe, relative to ROOT.
    path: Path
    # Its call script, such as corpus/X.calls or corpus/gen/sN.calls, relative to ROOT.
    calls_path: Path
    diff: DiffTest

    @classmethod
    def load(cls, path: Path) -> Self:
        """Returns the program at `path` with its call script.

        Errors when its name is no lowercase identifier, when it has no call script, or when it
        does not have exactly one contract.
        """
        path = path.relative_to(ROOT)
        script = calls_path(path)
        if not re.fullmatch(r"[a-z][a-z0-9_]*", path.stem):
            raise ScriptError(f"Errors when embedding {path}: the name must be a lowercase identifier")
        if not (ROOT / script).exists():
            raise ScriptError(f"Errors when embedding {path}: there is no {script.name}")
        source = FeSource((ROOT / path).read_text())
        contracts = CONTRACT.findall(source)
        if len(contracts) != 1:
            raise ScriptError(f"Errors when embedding {path}: it must have one contract")
        cases = parse_calls(ROOT / script, selectors(source))
        diff = DiffTest(TestName(f"corpus_{path.stem}"), FeName(contracts[0]), source, cases)
        return cls(path, script, diff)

    @property
    def test(self) -> TestName:
        return self.diff.test

    @property
    def runner(self) -> FeName:
        return self.diff.runner

    def module_text(self) -> FeSource:
        head = f"// Generated by tools/embed.py from {self.path} and {self.calls_path}."
        top = fegen.source([FeLine(head), fegen.difftest_use("fe0"), FeLine("")])
        return FeSource(top + self.diff.source + fegen.source([FeLine(""), *self.diff.lines()]))

    def explain(self, code: PanicCode) -> FailureMessage | None:
        f = Failure.decode(code)
        match f.kind:
            case Kind.PANIC:
                return None
            case Kind.DIAG:
                diag = DiagWord.unpack(code).describe(self.diff.source)
                return FailureMessage(f"{self.path}: Fe0 rejects it with {diag}")
            case Kind.PROBE:
                return FailureMessage(f"{self.path}: dispatcher probe {f.number} of fegen.DISPATCH:"
                                      " the builds differ")
        where = (f"{self.calls_path}:{f.number}" if f.number
                 else f"{self.calls_path}: the deployment without arguments")
        if f.kind is Kind.SIZE:
            return FailureMessage(f"{where}: Fe0's code is larger than a chain accepts")
        main = " or create no contract" if f.number == self.diff.cases.main.number else ""
        return FailureMessage(f"{where}: the builds differ{main}")


# The header lines of a reject program, which the module doc describes.
EXPECT = re.compile(rf"// expect: {fegen.CODE} {fegen.POS}")
FE_ACCEPTS = "// fe: accepts"


@dataclass
class Reject:
    """A reject program and the error that Fe0 must give for it."""

    # corpus/reject/X.fe, relative to ROOT.
    path: Path
    source: FeSource
    expected: DiagWord
    # Whether the header says `// fe: accepts`, so that the official compiler accepts it.
    fe_accepts: bool

    @classmethod
    def load(cls, path: Path) -> Self:
        """Returns the reject program at `path`.

        Errors when it has no `// expect:` header, or when the header names a line past its end.
        """
        path = path.relative_to(ROOT)
        return cls.parse(path, FeSource((ROOT / path).read_text()))

    @classmethod
    def parse(cls, path: Path, source: FeSource) -> Self:
        """Returns the reject program `source`, read from `path`, with the error its header names.

        Errors as `load` does.
        """
        lines = re.split(fegen.LINE_END, source)
        m = next(filter(None, map(EXPECT.fullmatch, lines)), None)
        if not m:
            raise ScriptError(f"Errors when embedding {path}: it has no `// expect: X000 line:col` header")
        try:
            expected = DiagWord.matched(m, source)
        except ValueError:
            raise ScriptError(f"Errors when embedding {path}: the header names line"
                              f" {LineCol.matched(m).line}, past the end") from None
        return cls(path, source, expected, FE_ACCEPTS in lines)

    @property
    def test(self) -> TestName:
        return TestName(f"reject_{self.path.stem}")

    def test_lines(self) -> list[FeLine]:
        """Returns the lines of the program's test."""
        return fegen.reject_test(self.test, self.source, self.expected)

    def official_failure(self, rejection: str | None) -> FailureMessage | None:
        """Returns a message when the result of `fe check` contradicts the `fe: accepts` header,
        or None when it agrees.

        `rejection` is the output of `fe check` when it rejects the program, or None when it
        accepts it.
        """
        if self.fe_accepts and rejection is not None:
            return FailureMessage(f"{self.path}: the official compiler rejects it, but the header"
                                  f" says `fe: accepts`\n{rejection}")
        if not self.fe_accepts and rejection is None:
            return FailureMessage(f"{self.path}: the official compiler accepts it; add"
                                  " `// fe: accepts` if Fe0 rejects it on purpose")
        return None

    def explain(self, code: PanicCode) -> FailureMessage | None:
        kind = Failure.decode(code).kind
        if kind is Kind.ACCEPTED:
            got = "accepts it"
        elif kind is Kind.DIAG:
            got = "gives " + DiagWord.unpack(code).describe(self.source)
        else:
            return None
        expected = self.expected.describe(self.source)
        return FailureMessage(f"{self.path}: Fe0 {got}, expected {expected}")


def reject_module(rejects: Iterable[Reject]) -> FeSource:
    """Returns the module that holds the tests of `rejects`."""
    out = [FeLine("// Generated by tools/embed.py from corpus/reject/."), fegen.difftest_use("fe0")]
    for r in rejects:
        out += r.test_lines()
    return fegen.source(out)


INGOT = """[ingot]
name = "{name}"
version = "0.1.0"

[dependencies]
fe0 = {{ path = "{fe0}" }}
"""


def write_ingot(d: Path, modules: Mapping[str, FeSource], lib: FeSource = FeSource("")) -> Path:
    """Writes an ingot named after the directory `d` into `d`, with `modules`, a dict from module
    name to text, and the root module `lib`."""
    (d / "src").mkdir(parents=True)
    fe0 = Path(os.path.relpath(fegen.FE0, d)).as_posix()
    (d / "fe.toml").write_text(INGOT.format(name=d.name, fe0=fe0))
    (d / "src/lib.fe").write_text(lib)
    # The modules are not formatted: Fe must compile each program as written, and `fe fmt`
    # breaks some long lines into code that Fe does not parse (docs/WORKAROUNDS.md).
    for m, text in modules.items():
        (d / f"src/{m}.fe").write_text(text)
    return d


def fe_rejection(path: Path) -> str | None:
    """Returns the output of the official compiler's `fe check` on the file `path` when it
    rejects the file, or None when it accepts it."""
    r = subprocess.run([fegen.FE, "check", "--standalone", str(ROOT / path)], capture_output=True, text=True)
    return None if r.returncode == 0 else r.stdout + r.stderr


# The line of `fe test` that reports a test as passed or failed, which captures the test's name.
# With several ingots, the line names the ingot first. A failed test's next line gives its revert
# data, the same on the EVM and on the native backend.
_RESULT = r"^{}\s+\[[^\]]*\]\s+(?:\w+\s+)?(\w+)"
_PASSED = re.compile(_RESULT.format("PASS") + "$", re.M)
_FAILED = re.compile(_RESULT.format("FAIL"))
_PANICKED = re.compile(_RESULT.format("FAIL") + r"\n\s+(?:\w+\s+)?Test reverted: 0x4e487b71([0-9a-f]{64})$",
                       re.M)


class TestRun(NamedTuple):
    """What `fe test` reports."""

    passed: set[TestName]
    # The panic code of each test that failed with one, by test name.
    panics: dict[TestName, PanicCode]
    output: str

    @classmethod
    def parse(cls, output: str) -> Self:
        """Returns what the output of `fe test` reports."""
        panics = {TestName(name): PanicCode(int(code, 16))
                  for name, code in _PANICKED.findall(output)}
        return cls({TestName(name) for name in _PASSED.findall(output)}, panics, output)

    def why(self, test: TestName) -> str:
        """Returns a sentence that quotes what the output says about the failure of `test`: the
        lines that report it, or the end of the output when no line names it."""
        lines = self.output.splitlines()
        start = next((i for i, line in enumerate(lines)
                      if (m := _FAILED.fullmatch(line)) and m[1] == test), None)
        if start is None:
            quote = self.output[-4000:]
        else:
            # The indented lines after the FAIL line belong to it.
            end = next((i for i in range(start + 1, len(lines)) if not lines[i][:1].isspace()), len(lines))
            quote = "\n".join(lines[start:end])
        return "fe test says why:\n" + quote


class Backend(Enum):
    """A backend of `fe test`, by the value of its `--backend` option."""

    # The default, which runs each test on the EVM.
    SONATINA = "sonatina"
    NATIVE = "native"


class FeTest(NamedTuple):
    """The `fe test` command of the harness."""

    # The optimization level.
    opt: OptLevel

    def run(self, ingots: Iterable[Path], only: str | None = None,
            backend: Backend = Backend.SONATINA) -> TestRun:
        """Runs the tests of `ingots` on `backend`, only those whose name holds `only` when it
        is given."""
        options = (["-f", only] if only else []) + ["--backend", backend.value]
        r = subprocess.run([fegen.FE, "test", "-O", self.opt, "--jobs", "0", *options, *map(str, ingots)],
                           capture_output=True, text=True)
        return TestRun.parse(r.stdout + r.stderr)


def report(tests: Mapping[TestName, Tested], run: TestRun) -> list[FailureMessage]:
    """Returns a message for each test that did not pass in `run`.

    `tests` maps each test name to its program. Stops at the first test that failed without a
    panic code.
    """
    failures: list[FailureMessage] = []
    for name in sorted(tests):
        if name in run.panics:
            code = run.panics[name]
            failures.append(tests[name].explain(code) or FailureMessage(
                f"{tests[name].path}: the test panicked with Panic({code:#04x})"))
        elif name not in run.passed:
            failures.append(FailureMessage(f"{name} did not pass, and {run.why(name)}"))
            break
    return failures


class Corpus(NamedTuple):
    """Programs and reject programs to run through the differential harness."""

    programs: list[Program]
    rejects: list[Reject]

    def check_official(self) -> "Checked":
        """Returns the verdict of `fe check` on the corpus, which it checks one file at a time."""
        with ThreadPoolExecutor() as pool:
            program_rejections = pool.map(fe_rejection, [p.path for p in self.programs])
            reject_rejections = pool.map(fe_rejection, [r.path for r in self.rejects])
            accepted: list[Program] = []
            failures: list[FailureMessage] = []
            for p, rejection in zip(self.programs, program_rejections):
                if rejection is None:
                    accepted.append(p)
                else:
                    failures.append(
                        FailureMessage(f"{p.path}: the official compiler rejects it\n{rejection}"))
            failures.extend(filter(None, map(Reject.official_failure, self.rejects, reject_rejections)))
        return Checked(accepted, failures)

    def write(self, out: Path) -> "Written":
        """Replaces the directory `out` with batch ingots of the programs that fe check accepts,
        and one ingot of all the reject programs. Returns them with a message for each failure
        of fe check."""
        checked = self.check_official()
        shutil.rmtree(out, ignore_errors=True)
        batches = [b.write() for b in Batch.split(out, checked.accepted)]
        reject = RejectIngot(out / "reject", self.rejects).write() if self.rejects else None
        print(f"{len(checked.accepted)} programs and {len(self.rejects)} reject programs"
              f" in {out.relative_to(ROOT)}/")
        return Written(batches, reject, checked.failures)

    def harness(self, out: Path, fe_test: FeTest | None) -> Never:
        """Runs the corpus through the differential harness, with the ingots in `out`, and exits
        with a message for each failure. The tests run with `fe_test`. When it is None, they do
        not run, and only the failures of fe check are reported."""
        written = self.write(out)
        failures = written.failures + (written.run(fe_test) if fe_test else [])
        sys.exit("\n".join(failures) or None)


class Checked(NamedTuple):
    """The verdict of the official compiler on a corpus."""

    # The programs that it accepts.
    accepted: list[Program]
    # A message for each program it rejects, and for each reject program whose header it
    # contradicts.
    failures: list[FailureMessage]


class Batch(NamedTuple):
    """A batch ingot and the programs in it."""

    ingot: Path
    programs: list[BatchProgram]

    @classmethod
    def split(cls, out: Path, programs: Sequence[BatchProgram]) -> list[Self]:
        """Returns the batches of `programs`, BATCH in each, in the directory `out`."""
        return [cls(out / f"batch{i:02}", list(group))
                for i, group in enumerate(itertools.batched(programs, BATCH), start=1)]

    @property
    def test(self) -> TestName:
        return TestName(BATCH_TEST + self.ingot.name)

    def write(self) -> Self:
        """Writes the ingot, with a module for each program and a root module that holds the
        batch test, and returns the batch."""
        calls = [FeLine(f"ingot::{p.path.stem}::{p.runner}()") for p in self.programs]
        test = fegen.evm_test(self.test, Wei(fegen.BALANCE * len(self.programs)), calls)
        lib = fegen.source([FeLine("// Generated by tools/embed.py."), FeLine(""), *test])
        write_ingot(self.ingot, {p.path.stem: p.module_text() for p in self.programs}, lib)
        return self


def run_batches(batches: list[Batch], fe_test: FeTest) -> list[FailureMessage]:
    """Runs the batch tests with `fe_test`, and returns a message for each program that fails.

    When a batch test fails, the tests of that batch's programs run too, and each program that
    fails gets its message from its own test. When every program of a failed batch passes
    alone, the batch gets one message instead, which quotes fe test on the batch test.
    """
    run = fe_test.run([b.ingot for b in batches], only=BATCH_TEST)
    passed: list[Batch] = []
    failed: list[Batch] = []
    for b in batches:
        (passed if b.test in run.passed else failed).append(b)
    rerun = fe_test.run([b.ingot for b in failed]) if failed else TestRun(set(), {}, "")
    alone = [p for b in failed for p in b.programs if p.test in rerun.passed]
    print(f"{sum(len(b.programs) for b in passed) + len(alone)} programs passed")
    failures: list[FailureMessage] = []
    for b in failed:
        failures += report({p.test: p for p in b.programs}, rerun) or [FailureMessage(
            f"{b.ingot.relative_to(ROOT)}: {b.test} fails, but each program passes alone, and"
            f" {run.why(b.test)}")]
    return failures


def load_rejects() -> list[Reject]:
    """Returns the reject programs of REJECTS, sorted by path. Exits with the message of the first
    one that does not load."""
    try:
        return [Reject.load(p) for p in sorted(REJECTS.glob("*.fe"))]
    except ScriptError as e:
        sys.exit(str(e))


class RejectIngot(NamedTuple):
    """The ingot of the reject programs."""

    ingot: Path
    rejects: list[Reject]

    def write(self) -> Self:
        """Writes the ingot and returns it."""
        write_ingot(self.ingot, {"reject": reject_module(self.rejects)})
        return self

    def run(self, fe_test: FeTest) -> list[FailureMessage]:
        """Runs the tests on the native backend with `fe_test`, and returns a message for each
        reject program that fails (DESIGN.md §10)."""
        tests = {r.test: r for r in self.rejects}
        run = fe_test.run([self.ingot], backend=Backend.NATIVE)
        print(f"{len(tests.keys() & run.passed)} reject programs passed")
        return report(tests, run)


class Written(NamedTuple):
    """The ingots of a corpus."""

    batches: list[Batch]
    # The ingot of the reject programs, or None when there are none.
    reject: RejectIngot | None
    # A message for each failure of `fe check`.
    failures: list[FailureMessage]

    def run(self, fe_test: FeTest) -> list[FailureMessage]:
        """Runs the tests of the ingots with `fe_test`, and returns a message for each program or
        reject program that did not pass."""
        failures = run_batches(self.batches, fe_test) if self.batches else []
        return failures + (self.reject.run(fe_test) if self.reject else [])


def parser(doc: str | None) -> argparse.ArgumentParser:
    """Returns a command-line parser with the options of the harness, -O and --no-run. The first
    line of the module docstring `doc` is its description. `doc` is None when Python runs with
    -OO, and the parser then has no description."""
    ap = argparse.ArgumentParser(
        description=doc.split("\n")[0] if doc else None,
        epilog="The environment variable FE gives the path of the fe binary (default: the fe on PATH).")
    ap.add_argument("-O", dest="opt", default="1", help="the optimization level of fe test")
    ap.add_argument("--no-run", action="store_true", help="skip fe test")
    return ap


def requested_fe_test(args: argparse.Namespace) -> FeTest | None:
    """Returns the fe test command that `args`, the options parsed by `parser`, ask for. Returns
    None when they hold --no-run."""
    return None if args.no_run else FeTest(OptLevel(args.opt))


def check_header() -> None:
    r"""Checks that both header lines end at `\r\n` and at a lone `\r`, as fe0 counts lines."""
    source = FeSource("// expect: E116 3:2\r\n// fe: accepts\rx\ryz")
    r = Reject.parse(Path("x.fe"), source)
    assert r.expected == DiagWord(DiagCode(PhaseLetter("E"), 116), ByteOffset(37)) and r.fe_accepts
    assert r.expected.describe(source) == "E116 3:2"


def main() -> None:
    fegen.check_diag_word()
    check_header()
    check_script_line()
    ap = parser(__doc__)
    ap.add_argument("names", nargs="*", metavar="NAME",
                    help="restricts the run to corpus/NAME.fe and corpus/reject/NAME.fe")
    args = ap.parse_args()
    wanted = set(args.names)

    def pick(paths: Iterable[Path]) -> list[Path]:
        return sorted(p for p in paths if not wanted or p.stem in wanted)

    try:
        programs = [Program.load(p) for p in pick(CORPUS.glob("*.fe"))]
        rejects = [Reject.load(p) for p in pick(REJECTS.glob("*.fe"))]
    except ScriptError as e:
        sys.exit(str(e))
    if not programs and not rejects:
        sys.exit("Errors when choosing programs: none matches " + " ".join(args.names))
    Corpus(programs, rejects).harness(OUT, requested_fe_test(args))

if __name__ == "__main__":
    main()
