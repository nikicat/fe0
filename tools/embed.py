#!/usr/bin/env python3
"""Run the corpus through the differential harness of DESIGN.md §10.

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
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import fegen
from fegen import MAX, ROOT, Call, Case, Cases, Deploy, DiagWord, DiffTest, Failure, Kind, RawCall

CORPUS = ROOT / "corpus"
OUT = ROOT / "out/difftest"
# Programs per batch ingot. DESIGN.md §11 measured batches of about 25 as the fastest layout.
BATCH = 25


class ScriptError(Exception):
    pass


# Integer expressions in call scripts.
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Pow: operator.pow,
       ast.LShift: operator.lshift, ast.RShift: operator.rshift, ast.FloorDiv: operator.floordiv,
       ast.BitOr: operator.or_, ast.BitAnd: operator.and_, ast.BitXor: operator.xor}
NAMES = {"MAX": MAX, "true": 1, "false": 0}


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


def selectors(source):
    """The selector of each msg variant in `source`, by variant name."""
    return {name: int(sel, 0)
            for sel, name in re.findall(r"#\[selector\s*=\s*(\w+)\]\s*(\w+)", source)}


def parse_calls(path, sels):
    """Returns what the call script `path` sends, with `sels` as the selectors by variant name.

    Each case's number is its line in the script. Without an `init` line, the main deployment is
    Case(0, Deploy()).
    """
    main, deploys, calls = Case(0, Deploy()), [], []
    for n, line in enumerate(path.read_text().splitlines(), start=1):
        words = line.split("#", 1)[0].split()
        if not words:
            continue
        try:
            head, args = words[0], words[1:]
            if head == "raw":
                if len(args) > 1 or not re.fullmatch(r"([0-9a-fA-F]{2})*", "".join(args)):
                    raise ScriptError("raw takes one string of hex bytes")
                calls.append(Case(n, RawCall(*bytes.fromhex("".join(args)))))
                continue
            kw = {}
            while args and re.fullmatch(r"(value|extra)=.*", args[-1]):
                k, v = args.pop().split("=", 1)
                kw[k] = word(v)
            vals = [word(a) for a in args]
            if head in ("init", "deploy"):
                d = Case(n, Deploy(*vals, **kw))
                if head == "deploy":
                    deploys.append(d)
                elif main.number:
                    raise ScriptError("a second init line")
                else:
                    main = d
            elif head in sels:
                calls.append(Case(n, Call(sels[head], *vals, **kw)))
            elif re.fullmatch(r"0x[0-9a-fA-F]+|[0-9]+", head):
                calls.append(Case(n, Call(int(head, 0), *vals, **kw)))
            else:
                raise ScriptError(f"{head} is no variant of the program")
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
    use = re.compile(rf'"(?:\\.|[^"\\])*"|//[^\n]*|\b({names})\b')
    return Renamed(use.sub(lambda m: f"{m[1]}_{suffix}" if m[1] else m[0], source),
                   [f"{name}_{suffix}" for kind, name in declared if kind == "contract"])


@dataclass
class Program:
    """A corpus program and the test that embed.py writes for it."""

    # corpus/X.fe, relative to ROOT.
    path: Path
    # corpus/X.calls, relative to ROOT.
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
        calls_path = path.with_suffix(".calls")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", path.stem):
            raise ScriptError(f"Errors when embedding {path}: the name must be a lowercase identifier")
        if not (ROOT / calls_path).exists():
            raise ScriptError(f"Errors when embedding {path}: there is no {calls_path.name}")
        source = (ROOT / path).read_text()
        module, contracts = rename(source, path.stem)
        if len(contracts) != 1:
            raise ScriptError(f"Errors when embedding {path}: it must have one contract")
        cases = parse_calls(ROOT / calls_path, selectors(source))
        return cls(path, calls_path, module, DiffTest(f"corpus_{path.stem}", contracts[0], source, cases))

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


def write_ingot(name, modules):
    """Writes the ingot `name` with `modules`, a dict from module name to text."""
    d = OUT / name
    (d / "src").mkdir(parents=True)
    (d / "fe.toml").write_text(INGOT.format(name=name, fe0="../../../fe0"))
    (d / "src/lib.fe").write_text("")
    for m, text in modules.items():
        fegen.write_formatted(d / f"src/{m}.fe", text)
    return d


def write_ingots(programs, rejects):
    """Replaces OUT with batch ingots of `programs` and one ingot of `rejects`, and returns
    their directories."""
    shutil.rmtree(OUT, ignore_errors=True)
    ingots = [write_ingot(f"batch{i:02}", {p.path.stem: p.module_text() for p in batch})
              for i, batch in enumerate(itertools.batched(programs, BATCH), start=1)]
    if rejects:
        ingots.append(write_ingot("reject", {"reject": reject_module(rejects)}))
    return ingots


def fe_rejection(path):
    """Returns the output of the official compiler's `fe check` on the file `path` when it
    rejects the file, or None when it accepts it."""
    r = subprocess.run([fegen.FE, "check", "--standalone", str(ROOT / path)], capture_output=True, text=True)
    return None if r.returncode == 0 else r.stdout + r.stderr


class Checked(NamedTuple):
    """The verdict of the official compiler on the corpus."""

    # The programs that it accepts.
    programs: list[Program]
    # A message for each program it rejects, and for each reject program whose header it
    # contradicts.
    failures: list[str]


def check_official(programs, rejects):
    """Returns the verdict of `fe check` on `programs` and `rejects`, which it checks one file
    at a time."""
    with ThreadPoolExecutor() as pool:
        program_rejections = pool.map(fe_rejection, [p.path for p in programs])
        reject_rejections = pool.map(fe_rejection, [r.path for r in rejects])
        checked = Checked([], [])
        for p, rejection in zip(programs, program_rejections):
            if rejection is None:
                checked.programs.append(p)
            else:
                checked.failures.append(f"{p.path}: the official compiler rejects it\n{rejection}")
        checked.failures.extend(filter(None, map(Reject.official_failure, rejects, reject_rejections)))
    return checked


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


def check_header():
    r"""Checks that both header lines end at `\r\n` and at a lone `\r`, as fe0 counts lines."""
    source = "// expect: E116 3:2\r\n// fe: accepts\rx\ryz"
    r = Reject.parse(Path("x.fe"), source)
    assert r.expected == DiagWord("E", 116, 37) and r.fe_accepts
    assert r.expected.describe(source) == "E116 3:2"


def main():
    fegen.check_diag_word()
    check_header()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 epilog="The environment variable FE gives the path of the fe binary (default ~/.fe/bin/fe).")
    ap.add_argument("-O", dest="opt", default="1", help="the optimization level of fe test")
    ap.add_argument("--no-run", action="store_true", help="only write the batch ingots")
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

    checked = check_official(programs, rejects)
    ingots = write_ingots(checked.programs, rejects)
    print(f"{len(checked.programs)} programs and {len(rejects)} reject programs in {OUT.relative_to(ROOT)}/")
    failures = checked.failures
    if not args.no_run:
        run = run_tests(ingots, args.opt)
        failures += report({t.test: t for t in checked.programs + rejects}, run)
        print(f"{len(run.passed)} tests passed")
    sys.exit("\n".join(failures) or None)

if __name__ == "__main__":
    main()
