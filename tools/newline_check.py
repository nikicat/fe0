#!/usr/bin/env python3
"""Check that Fe splits Fe0 programs into the same statements as Fe0 (SPEC.md §3.4).

In a program that Fe0 accepts, a statement ends at each newline whose innermost open bracket is
a `{`, and at the `}` that closes its block. So Fe0's statements follow from the brackets and
line ends alone. Fe's come from its own parser, through tools/fe-stmts (Fe's parser at the
release that the dev container pins). For each block that Fe parses, the two must hold the
same statements, at the same bytes.

The programs are the corpus, the reject programs that Fe0's parser accepts (their error comes
from a later phase), and generated programs. The generator writes one statement per line, so
each generated program is also checked reflowed: with line breaks at random places inside
parentheses, where Fe0 ignores them. The native CLI (fe0-cli) checks that Fe0 still accepts
each reflowed program.

usage: newline_check.py [--seeds N]
"""
import argparse
import random
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, NewType

import cli_check
from fegen import FE, ROOT, ByteOffset, FeSource, LineCol
from gen import Gen

FE_STMTS: Path = ROOT / "tools/fe-stmts"
FE_STMTS_TARGET: Path = ROOT / "out/fe-stmts"
FE_STMTS_EXE: Path = FE_STMTS_TARGET / "release/fe-stmts"
FE_STMTS_MANIFEST: Path = FE_STMTS / "Cargo.toml"
FE_STMTS_LOCK: Path = FE_STMTS / "Cargo.lock"
# A release of Fe, such as `26.7.0`.
FeVersion = NewType("FeVersion", str)
# The first line of `fe --version`, such as `fe 26.7.0 (e6e6342b2)`.
FE_VERSION = re.compile(r"fe (?P<version>\S+) ")
# The first line of a reject program names the error Fe0 gives, such as `// expect: T004 4:5`.
EXPECT = re.compile(r"// expect: (?P<letter>[A-Z])\d{3} ")
# Fe0's lexer and parser report errors with these letters. Other errors come later, from a
# program that Fe0 parsed.
PARSE_LETTERS = {"L", "P"}
# The tokens that matter here, as Fe0's lexer reads them: comments, string literals (which may
# hold brackets), line ends, brackets, and any other byte that is not white space.
TOKEN = re.compile(rb'(?P<comment>//[^\r\n]*)|(?P<string>"(?:[^"\\\r\n]|\\.)*")'
                   rb"|(?P<newline>\r\n?|\n)|(?P<space>[ \t]+)"
                   rb"|(?P<open>[({\[])|(?P<close>[)}\]])|(?P<other>.)")


class Span(NamedTuple):
    """The bytes of one statement, from its first token to the end of its last."""

    start: ByteOffset
    end: ByteOffset


# The statements of each block, by the offset of the block's `{`.
Blocks = dict[ByteOffset, list[Span]]


@dataclass
class Frame:
    """An open bracket, and for a `{`, the statement it is reading."""

    bracket: bytes
    offset: ByteOffset
    stmts: list[Span] = field(default_factory=list)
    start: ByteOffset | None = None
    end: ByteOffset = ByteOffset(0)

    def take(self, start: ByteOffset, end: ByteOffset) -> None:
        """Adds the token at `start`..`end` to the statement this block is reading."""
        if self.start is None:
            self.start = start
        self.end = end

    def finish(self) -> None:
        """Ends the statement this block is reading, if it has one."""
        if self.start is not None:
            self.stmts.append(Span(self.start, self.end))
            self.start = None


def fe0_blocks(source: FeSource) -> Blocks:
    """Returns the statements of each block of `source`, as Fe0 reads them when it accepts
    `source`."""
    blocks: Blocks = {}
    stack: list[Frame] = []

    def take(start: ByteOffset, end: ByteOffset) -> None:
        """Adds a token to the statement of the innermost block, which a `(` or `[` inside it
        does not end."""
        block = next((f for f in reversed(stack) if f.bracket == b"{"), None)
        if block is not None:
            block.take(start, end)

    for m in TOKEN.finditer(source.encode()):
        start, end = ByteOffset(m.start()), ByteOffset(m.end())
        if m["newline"] is not None:
            if stack and stack[-1].bracket == b"{":
                stack[-1].finish()
        elif m["open"] is not None:
            take(start, end)
            stack.append(Frame(m["open"], start))
        elif m["close"] is not None:
            frame = stack.pop()
            if frame.bracket == b"{":
                frame.finish()
                blocks[frame.offset] = frame.stmts
            take(start, end)
        elif m["comment"] is None and m["space"] is None:
            take(start, end)
    return blocks


# Fe0's binary operators, as `Tok.is_binary` in fe0/src/lexer.fe names them. Inside
# parentheses, a line may end with one.
BINARY_OPS = {b"+", b"-", b"*", b"/", b"%", b"&", b"|", b"^", b"<<", b">>", b"<", b">", b"<=",
              b">=", b"==", b"!=", b"&&", b"||"}


def reflow(source: FeSource, rng: random.Random) -> FeSource:
    """Returns `source` with a line break in about half of the places inside parentheses where
    Fe0 allows one: after a `(`, a `,` or a binary operator, and before a `)`."""
    data = source.encode()
    out = bytearray()
    stack: list[bytes] = []
    last = 0

    def maybe_break(at: int, replace: int) -> None:
        """Puts a line break at `at` in place of `replace` bytes, half of the time."""
        nonlocal last
        if stack and stack[-1] == b"(" and rng.random() < 0.5:
            out.extend(data[last:at] + b"\n")
            last = at + replace

    for m in TOKEN.finditer(data):
        if m["open"] is not None:
            stack.append(m["open"])
            maybe_break(m.end(), 0)
        elif m["close"] is not None:
            maybe_break(m.start(), 0)
            stack.pop()
        elif m["space"] is not None:
            word = data[:m.start()].rsplit(None, 1)[-1]
            if word.endswith(b",") or word in BINARY_OPS:
                maybe_break(m.start(), m.end() - m.start())
    out.extend(data[last:])
    return FeSource(out.decode())


def fe_version() -> FeVersion:
    """Returns the release of the fe binary. Errors with ValueError when `fe --version` prints
    no release."""
    out = subprocess.run([FE, "--version"], check=True, capture_output=True, text=True).stdout
    m = FE_VERSION.match(out)
    if m is None:
        raise ValueError(f"{FE} --version prints no release: {out.strip()}")
    return FeVersion(m["version"])


def locked_parser_version() -> FeVersion:
    """Returns the release of fe-parser that FE_STMTS_LOCK locks. Errors with ValueError when
    the lock has no fe-parser."""
    lock = tomllib.loads(FE_STMTS_LOCK.read_text())
    version = next((p["version"] for p in lock["package"] if p["name"] == "fe-parser"), None)
    if version is None:
        raise ValueError(f"{FE_STMTS_LOCK} locks no fe-parser")
    return FeVersion(version)


def check_parser_version() -> None:
    """Checks that tools/fe-stmts parses with the parser of the fe binary's release, which
    .devcontainer/Containerfile pins. Exits with a message when the two releases differ."""
    fe, parser = fe_version(), locked_parser_version()
    if fe != parser:
        sys.exit(f"{FE} is Fe {fe}, but {FE_STMTS_LOCK.relative_to(ROOT)} locks fe-parser"
                 f" {parser}: pin the same release in .devcontainer/Containerfile and"
                 f" {FE_STMTS_MANIFEST.relative_to(ROOT)}")


def fe_stmts() -> Path:
    """Builds tools/fe-stmts and returns its executable. Errors when the build fails."""
    subprocess.run(["cargo", "build", "--quiet", "--release", "--manifest-path",
                    str(FE_STMTS_MANIFEST), "--target-dir", str(FE_STMTS_TARGET)],
                   check=True)
    return FE_STMTS_EXE


class FeParseError(Exception):
    """Fe's parser rejects a program."""


def fe_blocks(exe: Path, path: Path) -> Blocks:
    """Returns the statements of each block of the program at `path`, as Fe's parser reads
    them. Errors with FeParseError when Fe's parser rejects the program."""
    result = subprocess.run([str(exe), str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise FeParseError(result.stderr.strip())
    blocks: Blocks = {}
    for line in result.stdout.splitlines():
        open_brace, *stmts = line.split(" ")
        blocks[ByteOffset(int(open_brace))] = [
            Span(ByteOffset(int(s)), ByteOffset(int(e)))
            for s, e in (stmt.split("-") for stmt in stmts if stmt)]
    return blocks


def differences(source: FeSource, fe0: Blocks, fe: Blocks) -> list[str]:
    """Returns a line for each block of `fe` whose statements differ from `fe0`'s, with the
    first statement where they differ."""
    out = []
    data = source.encode()

    def show(stmts: list[Span], i: int) -> str:
        if i >= len(stmts):
            return "no statement"
        s = stmts[i]
        return repr(data[s.start:s.end].decode())

    for offset, stmts in fe.items():
        ours = fe0.get(offset)
        if ours == stmts:
            continue
        if ours is None:
            out.append(f"{LineCol.of(offset, source)}: Fe reads a block that Fe0 does not")
            continue
        i = next(i for i in range(max(len(ours), len(stmts)))
                 if i >= len(ours) or i >= len(stmts) or ours[i] != stmts[i])
        at = min(r[i].start for r in (ours, stmts) if i < len(r))
        out.append(f"{LineCol.of(at, source)}: Fe0 reads {show(ours, i)},"
                   f" Fe reads {show(stmts, i)}")
    return out


class Program(NamedTuple):
    """A program to check, with the path that names it in the report."""

    path: Path
    source: FeSource


def corpus() -> list[Program]:
    """Returns the corpus programs and the reject programs that Fe0's parser accepts."""
    programs = [Program(p, FeSource(p.read_text())) for p in sorted((ROOT / "corpus").glob("*.fe"))]
    for p in sorted((ROOT / "corpus/reject").glob("*.fe")):
        text = FeSource(p.read_text())
        m = EXPECT.match(text)
        if m is None:
            raise ValueError(f"{p} has no `// expect:` line")
        if m["letter"] not in PARSE_LETTERS:
            programs.append(Program(p, text))
    return programs


def generated(seeds: int, out: Path) -> list[Program]:
    """Writes the generated programs of seeds 1 to `seeds` to `out`, each also reflowed, and
    returns them."""
    out.mkdir(parents=True, exist_ok=True)
    programs = []
    for seed in range(1, seeds + 1):
        source = FeSource(Gen(seed).program().program)
        for path, text in [(out / f"s{seed}.fe", source),
                           (out / f"s{seed}_reflowed.fe", reflow(source, random.Random(seed)))]:
            path.write_text(text)
            programs.append(Program(path, text))
    return programs


def rejected_reflows(programs: list[Program]) -> list[str]:
    """Returns a line for each reflowed program that Fe0's native CLI does not compile."""
    cli_check.build()
    out = []
    for p in programs:
        if p.path.stem.endswith("_reflowed"):
            run = cli_check.Run.of(p.path, p.source)
            if not run.compiled():
                out.append(f"{p.path.relative_to(ROOT)}: Fe0 rejects it: {run.stderr.strip()}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=500,
                    help="the number of generated programs (default 500)")
    args = ap.parse_args()
    check_parser_version()
    exe = fe_stmts()
    programs = corpus() + generated(args.seeds, ROOT / "out/newline-check")
    rejected = rejected_reflows(programs)
    for line in rejected:
        print(line)
    failed = len(rejected)
    blocks = 0
    for p in programs:
        name = p.path.relative_to(ROOT)
        try:
            fe = fe_blocks(exe, p.path)
        except FeParseError as e:
            print(f"{name}: {e}")
            failed += 1
            continue
        diffs = differences(p.source, fe0_blocks(p.source), fe)
        blocks += len(fe)
        for d in diffs:
            print(f"{name}:{d}")
        failed += bool(diffs)
    print(f"{len(programs)} programs, {blocks} blocks: {failed} differ")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
