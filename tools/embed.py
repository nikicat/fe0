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
`2**255` or `MAX-1`, and its value must fit in 256 bits. Any entry but `raw` may end with
`value=N`, the wei sent with it, and `extra=N`, a number of bytes appended after the words.
Without an `init` line, the main deployment has no arguments. Every program also gets the calls
of `fegen.DISPATCH`.

Each reject program `corpus/reject/X.fe` names the error that Fe0 must give, in a header line:

    // expect: E116 12:9

The header gives the error code, then the line and column where the error points. Both count
from 1, and the column counts bytes. Another header line, `// fe: accepts`, marks a rule that
Fe0 adds on top of Fe, so the official compiler must accept the program (SPEC.md §8).
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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import NamedTuple

import fegen
from fegen import MAX, ROOT, Call, Case, Cases, Deploy, DiagWord, DiffTest, Failure, Kind, RawCall

CORPUS = ROOT / "corpus"
OUT = ROOT / "out/difftest"
# Programs per batch ingot (ADR 0003, Measurements).
BATCH = 25


class ScriptError(Exception):
    pass


# Integer expressions in call scripts.
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Pow: operator.pow,
       ast.LShift: operator.lshift, ast.RShift: operator.rshift, ast.FloorDiv: operator.floordiv,
       ast.BitOr: operator.or_, ast.BitAnd: operator.and_, ast.BitXor: operator.xor}
_MAX_WORD = "MAX"
NAMES = {_MAX_WORD: MAX, "true": 1, "false": 0}


def word(text):
    """Returns the word that the argument `text` gives.

    Errors when `text` is not an integer expression of the call-script form, or when its value
    does not fit in 256 bits.
    """
    def ev(n):
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
    return v


# A Fe0 line comment, as Lexer.skip_trivia reads it (SPEC §1).
LINE_COMMENT = re.compile(r"//[^\r\n]*")


def selectors(source):
    """Returns the selector of each msg variant in `source`, by variant name."""
    return {name: int(sel, 0)
            for sel, name in re.findall(r"#\[selector\s*=\s*(\w+)\]\s*(\w+)",
                                        LINE_COMMENT.sub("", source))}


class Head(Enum):
    """A keyword that starts a call-script entry."""

    INIT = "init"
    DEPLOY = "deploy"
    RAW = "raw"


_OPTIONS = ("value", "extra")


class ScriptLine(NamedTuple):
    """One entry of a call script."""

    # A keyword, a variant name, or a selector.
    head: Head | str | int
    # The argument words, or the bytes of a `raw` entry.
    words: tuple[int, ...] = ()
    # The wei sent with the entry.
    value: int = 0
    # The number of bytes appended after the words.
    extra: int = 0

    def render(self):
        """The text of the entry, without a line end."""
        if self.head is Head.RAW:
            return f"{Head.RAW.value} {bytes(self.words).hex()}"
        match self.head:
            case Head():
                head = self.head.value
            case int(sel):
                head = f"{sel:#x}"
            case name:
                head = name
        opts = [f"{k}={_render_word(v)}" for k, v in zip(_OPTIONS, (self.value, self.extra)) if v]
        return " ".join([head, *map(_render_word, self.words), *opts])

    @classmethod
    def parse(cls, text):
        """Returns the entry that the line `text` gives, or None for a blank or comment line.

        Errors when the line is not of the call-script form.
        """
        tokens = text.split("#", 1)[0].split()
        if not tokens:
            return None
        head, args = tokens[0], tokens[1:]
        if head == Head.RAW.value:
            if len(args) > 1 or not re.fullmatch(r"([0-9a-fA-F]{2})*", "".join(args)):
                raise ScriptError(f"{Head.RAW.value} takes one string of hex bytes")
            return cls(Head.RAW, tuple(bytes.fromhex("".join(args))))
        opts = {}
        while args and re.fullmatch(rf"({'|'.join(_OPTIONS)})=.*", args[-1]):
            k, v = args.pop().split("=", 1)
            opts[k] = word(v)
        if head in (Head.INIT.value, Head.DEPLOY.value):
            head = Head(head)
        elif re.fullmatch(r"0x[0-9a-fA-F]+|[0-9]+", head):
            head = int(head, 0)
        return cls(head, tuple(word(a) for a in args), **opts)


def _render_word(w):
    """The argument text of the word `w`: MAX by name, large words in hex, others in decimal."""
    if w == MAX:
        return _MAX_WORD
    return f"{w:#x}" if w >= 2**64 else str(w)


def check_script_line():
    """Checks that rendered call-script entries parse back to the same entries."""
    for line in [ScriptLine(Head.INIT, (5, 1)), ScriptLine(Head.DEPLOY, (2,), value=7, extra=3),
                 ScriptLine("Set", (MAX, 2**200)), ScriptLine(0x2a), ScriptLine(Head.RAW, (0, 0x2a))]:
        assert ScriptLine.parse(line.render()) == line, line


def parse_calls(path, sels):
    """Returns what the call script `path` sends, with `sels` as the selectors by variant name.

    Each case's number is its line in the script. Without an `init` line, the main deployment is
    Case(0, Deploy()).
    """
    main, deploys, calls = Case(0, Deploy()), [], []
    for n, text in enumerate(path.read_text().splitlines(), start=1):
        try:
            line = ScriptLine.parse(text)
            if line is None:
                continue
            words, opts = line.words, dict(value=line.value, extra=line.extra)
            match line.head:
                case Head.RAW:
                    calls.append(Case(n, RawCall(*words)))
                case Head.DEPLOY:
                    deploys.append(Case(n, Deploy(*words, **opts)))
                case Head.INIT if main.number:
                    raise ScriptError(f"a second {Head.INIT.value} line")
                case Head.INIT:
                    main = Case(n, Deploy(*words, **opts))
                case int(sel):
                    calls.append(Case(n, Call(sel, *words, **opts)))
                case name if name in sels:
                    calls.append(Case(n, Call(sels[name], *words, **opts)))
                case name:
                    raise ScriptError(f"{name} is no variant of the program")
        except ScriptError as e:
            raise ScriptError(f"{path.relative_to(ROOT)}:{n}: {e}") from None
    return Cases(main, deploys, calls)


class Renamed(NamedTuple):
    """A program with its contracts and msgs renamed."""

    source: str
    # The new names of its contracts.
    contracts: list[str]


DECLARATION = re.compile(r"^\s*(?:pub\s+)?(contract|msg)\s+(\w+)", re.M)


def rename(source, suffix):
    """Gives each contract and msg of `source` the name `Name_suffix`, outside string literals
    and comments.

    Contract and msg names must be unique across an ingot (WORKAROUNDS.md).
    """
    declared = DECLARATION.findall(source)
    if not declared:
        return Renamed(source, [])
    names = "|".join(name for _, name in declared)
    use = re.compile(rf'"(?:\\.|[^"\\])*"|{LINE_COMMENT.pattern}|\b({names})\b')
    return Renamed(use.sub(lambda m: f"{m[1]}_{suffix}" if m[1] else m[0], source),
                   [f"{name}_{suffix}" for kind, name in declared if kind == "contract"])


def calls_path(program):
    """Returns the path of the call script that lies beside the program at `program`."""
    return program.with_suffix(".calls")


@dataclass
class Program:
    """A program with a call script, and the test that embed.py writes for it."""

    # The program, such as corpus/X.fe or corpus/gen/sN.fe, relative to ROOT.
    path: Path
    # Its call script, such as corpus/X.calls or corpus/gen/sN.calls, relative to ROOT.
    calls_path: Path
    # The program with its contracts and msgs renamed (`rename`), which Fe compiles.
    module: str
    diff: DiffTest

    @classmethod
    def load(cls, path):
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
        source = (ROOT / path).read_text()
        module, contracts = rename(source, path.stem)
        if len(contracts) != 1:
            raise ScriptError(f"Errors when embedding {path}: it must have one contract")
        cases = parse_calls(ROOT / script, selectors(source))
        return cls(path, script, module, DiffTest(f"corpus_{path.stem}", contracts[0], source, cases))

    @property
    def test(self):
        return self.diff.test

    def module_text(self):
        """Returns the module of the batch ingot that holds the program and its test."""
        return "\n".join([f"// Generated by tools/embed.py from {self.path} and {self.calls_path}.",
                          fegen.difftest_use("fe0"), "", self.module] + self.diff.lines()) + "\n"

    def explain(self, code):
        """Returns what the failure Panic(`code`) of the program's test means."""
        f = Failure.decode(code)
        match f.kind:
            case Kind.PANIC:
                return f"{self.path}: the test panicked with Panic({code:#04x})"
            case Kind.DIAG:
                return f"{self.path}: Fe0 rejects it with {DiagWord.unpack(code).describe(self.diff.source)}"
            case Kind.PROBE:
                return f"{self.path}: dispatcher probe {f.number} of fegen.DISPATCH: the builds differ"
        where = (f"{self.calls_path}:{f.number}" if f.number
                 else f"{self.calls_path}: the deployment without arguments")
        if f.kind is Kind.SIZE:
            return f"{where}: Fe0's code is larger than a chain accepts"
        main = " or create no contract" if f.number == self.diff.cases.main.number else ""
        return f"{where}: the builds differ{main}"


# The header lines of a reject program, which the module doc describes.
EXPECT = re.compile(r"// expect: ([A-Z])(\d{3}) (\d+):(\d+)")
FE_ACCEPTS = "// fe: accepts"


@dataclass
class Reject:
    """A reject program and the error that Fe0 must give for it."""

    # corpus/reject/X.fe, relative to ROOT.
    path: Path
    source: str
    expected: DiagWord
    # Whether the header says `// fe: accepts`, so that the official compiler accepts it.
    fe_accepts: bool

    @classmethod
    def load(cls, path):
        """Returns the reject program at `path`.

        Errors when it has no `// expect:` header, or when the header names a line past its end.
        """
        path = path.relative_to(ROOT)
        return cls.parse(path, (ROOT / path).read_text())

    @classmethod
    def parse(cls, path, source):
        """Returns the reject program `source`, read from `path`, with the error its header names.

        Errors as `load` does.
        """
        lines = re.split(fegen.LINE_END, source)
        m = next(filter(None, map(EXPECT.fullmatch, lines)), None)
        if not m:
            raise ScriptError(f"Errors when embedding {path}: it has no `// expect: X000 line:col` header")
        try:
            expected = DiagWord.at(m[1], int(m[2]), int(m[3]), int(m[4]), source)
        except ValueError:
            raise ScriptError(f"Errors when embedding {path}: the header names line {m[3]}, past the end") from None
        return cls(path, source, expected, FE_ACCEPTS in lines)

    @property
    def test(self):
        return f"reject_{self.path.stem}"

    def test_lines(self):
        """Returns the lines of the program's test."""
        return fegen.reject_test(self.test, self.source, self.expected)

    def official_failure(self, rejection):
        """Returns a message when the result of `fe check` contradicts the `fe: accepts` header,
        or None when it agrees.

        `rejection` is the output of `fe check` when it rejects the program, or None when it
        accepts it.
        """
        if self.fe_accepts and rejection is not None:
            return f"{self.path}: the official compiler rejects it, but the header says `fe: accepts`\n{rejection}"
        if not self.fe_accepts and rejection is None:
            return f"{self.path}: the official compiler accepts it; add `// fe: accepts` if Fe0 rejects it on purpose"
        return None

    def explain(self, code):
        """Returns what the failure Panic(`code`) of the program's test means."""
        kind = Failure.decode(code).kind
        if kind is Kind.ACCEPTED:
            got = "accepts it"
        elif kind is Kind.DIAG:
            got = "gives " + DiagWord.unpack(code).describe(self.source)
        else:
            return f"{self.path}: the test panicked with Panic({code:#04x})"
        return f"{self.path}: Fe0 {got}, expected {self.expected.describe(self.source)}"


def reject_module(rejects):
    """Returns the module that holds the tests of `rejects`."""
    out = ["// Generated by tools/embed.py from corpus/reject/.", fegen.difftest_use("fe0")]
    for r in rejects:
        out += r.test_lines()
    return "\n".join(out) + "\n"


INGOT = """[ingot]
name = "{name}"
version = "0.1.0"

[dependencies]
fe0 = {{ path = "{fe0}" }}
"""


def write_ingot(d, modules):
    """Writes an ingot named after the directory `d` into `d`, with `modules`, a dict from module
    name to text."""
    (d / "src").mkdir(parents=True)
    fe0 = Path(os.path.relpath(fegen.FE0, d)).as_posix()
    (d / "fe.toml").write_text(INGOT.format(name=d.name, fe0=fe0))
    (d / "src/lib.fe").write_text("")
    # The modules are not formatted: Fe must compile each program as written, and `fe fmt`
    # breaks some long lines into code that Fe does not parse (docs/WORKAROUNDS.md).
    for m, text in modules.items():
        (d / f"src/{m}.fe").write_text(text)
    return d


def fe_rejection(path):
    """Returns the output of the official compiler's `fe check` on the file `path` when it
    rejects the file, or None when it accepts it."""
    r = subprocess.run([fegen.FE, "check", "--standalone", str(ROOT / path)], capture_output=True, text=True)
    return None if r.returncode == 0 else r.stdout + r.stderr


class TestRun(NamedTuple):
    """What `fe test` reports."""

    passed: set[str]
    # The panic code of each test that failed with one, by test name.
    panics: dict[str, int]
    output: str


def run_tests(ingots, opt):
    """Runs `fe test` at the optimization level `opt` on `ingots`."""
    r = subprocess.run([fegen.FE, "test", "-O", opt, "--jobs", "0", *map(str, ingots)],
                       capture_output=True, text=True)
    out = r.stdout + r.stderr
    # With several ingots, `fe test` prints the ingot's name before the test's.
    panics = re.findall(r"^FAIL\s+\[[^\]]*\]\s+(?:\w+\s+)?(\w+)\n\s+(?:\w+\s+)?"
                        r"Test reverted: 0x4e487b71([0-9a-f]{64})$", out, re.M)
    passed = set(re.findall(r"^PASS\s+\[[^\]]*\]\s+(?:\w+\s+)?(\w+)$", out, re.M))
    return TestRun(passed, {name: int(code, 16) for name, code in panics}, out)


def report(tests, run):
    """Returns a message for each test that did not pass in `run`.

    `tests` maps each test name to its Program or Reject. Stops at the first test that failed
    without a panic code.
    """
    failures = []
    for name in sorted(tests):
        if name in run.panics:
            failures.append(tests[name].explain(run.panics[name]))
        elif name not in run.passed:
            failures.append(f"{name} did not pass, and fe test says why:\n" + run.output[-4000:])
            break
    return failures


class Corpus(NamedTuple):
    """Programs and reject programs to run through the differential harness."""

    programs: list[Program]
    rejects: list[Reject]

    def check_official(self):
        """Returns the verdict of `fe check` on the corpus, which it checks one file at a time."""
        with ThreadPoolExecutor() as pool:
            program_rejections = pool.map(fe_rejection, [p.path for p in self.programs])
            reject_rejections = pool.map(fe_rejection, [r.path for r in self.rejects])
            accepted, failures = [], []
            for p, rejection in zip(self.programs, program_rejections):
                if rejection is None:
                    accepted.append(p)
                else:
                    failures.append(f"{p.path}: the official compiler rejects it\n{rejection}")
            failures.extend(filter(None, map(Reject.official_failure, self.rejects, reject_rejections)))
        return Checked(Corpus(accepted, self.rejects), failures)

    def write_ingots(self, out):
        """Replaces the directory `out` with batch ingots of the programs and one ingot of the
        reject programs, and returns their directories."""
        shutil.rmtree(out, ignore_errors=True)
        ingots = [write_ingot(out / f"batch{i:02}", {p.path.stem: p.module_text() for p in batch})
                  for i, batch in enumerate(itertools.batched(self.programs, BATCH), start=1)]
        if self.rejects:
            ingots.append(write_ingot(out / "reject", {"reject": reject_module(self.rejects)}))
        return ingots

    def write(self, out):
        """Writes to `out` the batch ingots of the programs that fe check accepts, and one ingot
        of all the reject programs. Returns them with a message for each failure of fe check."""
        checked = self.check_official()
        ingots = checked.corpus.write_ingots(out)
        print(f"{len(checked.corpus.programs)} programs and {len(self.rejects)} reject programs"
              f" in {out.relative_to(ROOT)}/")
        return Written(checked.corpus, ingots, checked.failures)

    def harness(self, out, args):
        """Runs the corpus through the differential harness, with the ingots in `out`, and exits
        with a message for each failure. `args` holds the options of `parser`. When
        `args.no_run` is set, fe test does not run, and only the failures of fe check are
        reported."""
        written = self.write(out)
        failures = written.failures if args.no_run else written.failures + written.run(args.opt)
        sys.exit("\n".join(failures) or None)


class Checked(NamedTuple):
    """The verdict of the official compiler on a corpus."""

    # The programs that it accepts, and all the reject programs.
    corpus: Corpus
    # A message for each program it rejects, and for each reject program whose header it
    # contradicts.
    failures: list[str]


class Written(NamedTuple):
    """The batch ingots of a corpus, and the programs and reject programs in them."""

    corpus: Corpus
    ingots: list[Path]
    # A message for each failure of `fe check`.
    failures: list[str]

    def run(self, opt):
        """Runs `fe test` at the optimization level `opt` on the ingots, and returns a message
        for each test that did not pass."""
        run = run_tests(self.ingots, opt)
        print(f"{len(run.passed)} tests passed")
        return report({t.test: t for t in self.corpus.programs + self.corpus.rejects}, run)


def parser(doc):
    """Returns a command-line parser with the options of the harness, -O and --no-run. The first
    line of the module docstring `doc` is its description."""
    ap = argparse.ArgumentParser(
        description=doc.split("\n")[0],
        epilog=f"The environment variable FE gives the path of the fe binary (default {fegen.FE_DEFAULT}).")
    ap.add_argument("-O", dest="opt", default="1", help="the optimization level of fe test")
    ap.add_argument("--no-run", action="store_true", help="skip fe test (fe check still runs)")
    return ap


def check_header():
    r"""Checks that both header lines end at `\r\n` and at a lone `\r`, as fe0 counts lines."""
    source = "// expect: E116 3:2\r\n// fe: accepts\rx\ryz"
    r = Reject.parse(Path("x.fe"), source)
    assert r.expected == DiagWord("E", 116, 37) and r.fe_accepts
    assert r.expected.describe(source) == "E116 3:2"


def main():
    fegen.check_diag_word()
    check_header()
    check_script_line()
    ap = parser(__doc__)
    ap.add_argument("names", nargs="*", metavar="NAME",
                    help="restricts the run to corpus/NAME.fe and corpus/reject/NAME.fe")
    args = ap.parse_args()
    wanted = set(args.names)
    pick = lambda paths: sorted(p for p in paths if not wanted or p.stem in wanted)
    try:
        programs = [Program.load(p) for p in pick(CORPUS.glob("*.fe"))]
        rejects = [Reject.load(p) for p in pick((CORPUS / "reject").glob("*.fe"))]
    except ScriptError as e:
        sys.exit(str(e))
    if not programs and not rejects:
        sys.exit("Errors when choosing programs: none matches " + " ".join(args.names))
    Corpus(programs, rejects).harness(OUT, args)

if __name__ == "__main__":
    main()
