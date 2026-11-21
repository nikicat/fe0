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
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, NewType

import cli_check
import embed
from fegen import FE, ROOT, ByteOffset, FeSource, LineCol
from fetokens import Kind, Op, Token, tokens
from gen import Gen, Seed, program_file, seeds_from
from mutate import Text, reflow

FE_STMTS: Path = ROOT / "tools/fe-stmts"
FE_STMTS_TARGET: Path = ROOT / "out/fe-stmts"
FE_STMTS_EXE: Path = FE_STMTS_TARGET / "release/fe-stmts"
FE_STMTS_MANIFEST: Path = FE_STMTS / "Cargo.toml"
FE_STMTS_LOCK: Path = FE_STMTS / "Cargo.lock"
# A release of Fe, such as `26.7.0`.
FeVersion = NewType("FeVersion", str)
# The first line of `fe --version`, such as `fe 26.7.0 (e6e6342b2)`.
FE_VERSION = re.compile(r"fe (?P<version>\S+) ")


class Span(NamedTuple):
    """The bytes of one statement, from its first token to the end of its last."""

    start: ByteOffset
    end: ByteOffset


# The statements of each block, by the offset of the block's `{`.
Blocks = dict[ByteOffset, list[Span]]


@dataclass
class Frame:
    """An open bracket, and for a `{`, the statement it is reading."""

    bracket: Token
    stmts: list[Span] = field(default_factory=list)
    start: ByteOffset | None = None
    end: ByteOffset = ByteOffset(0)

    @property
    def is_block(self) -> bool:
        return self.bracket.symbol == Op.LBRACE

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
        block = next((f for f in reversed(stack) if f.is_block), None)
        if block is not None:
            block.take(start, end)

    for t in tokens(source.encode()):
        match t.kind:
            case Kind.NEWLINE:
                if stack and stack[-1].is_block:
                    stack[-1].finish()
            case Kind.OPEN:
                take(t.start, t.end)
                stack.append(Frame(t))
            case Kind.CLOSE:
                frame = stack.pop()
                if frame.is_block:
                    frame.finish()
                    blocks[frame.bracket.start] = frame.stmts
                take(t.start, t.end)
            case _ if not t.kind.trivia:
                take(t.start, t.end)
    return blocks


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


class FeBlock(NamedTuple):
    """One block of a program, as Fe's parser reads it."""

    open_brace: ByteOffset
    stmts: list[Span]

    @classmethod
    def parse(cls, line: str) -> "FeBlock":
        """Returns the block on one line that tools/fe-stmts prints, in the format that the doc
        of tools/fe-stmts/src/main.rs states. Errors with ValueError when `line` is not in
        that format."""
        try:
            open_brace, *stmts = line.split()
            return cls(ByteOffset(int(open_brace)),
                       [Span(ByteOffset(int(s)), ByteOffset(int(e)))
                        for s, e in (stmt.split("-") for stmt in stmts)])
        except ValueError as e:
            raise ValueError(f"fe-stmts prints a line that is not a block: {line!r}") from e


class FeParseError(Exception):
    """Fe's parser rejects a program."""


def fe_blocks(exe: Path, path: Path) -> Blocks:
    """Returns the statements of each block of the program at `path`, as Fe's parser reads
    them. Errors with FeParseError when Fe's parser rejects the program, and as FeBlock.parse
    does on a line of tools/fe-stmts."""
    result = subprocess.run([str(exe), str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise FeParseError(result.stderr.strip())
    return dict(FeBlock.parse(line) for line in result.stdout.splitlines())


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
    # True if the program is a generated one with line breaks added inside parentheses. False
    # otherwise.
    reflowed: bool = False


def corpus() -> list[Program]:
    """Returns the corpus programs and the reject programs that Fe0's parser accepts."""
    programs = [Program(p, FeSource(p.read_text())) for p in sorted(embed.CORPUS.glob("*.fe"))]
    return programs + [Program(ROOT / r.path, r.source) for r in embed.load_rejects()
                       if not r.expected.code.is_syntax]


def generated(seeds: Iterable[Seed], out: Path) -> list[Program]:
    """Writes the generated programs of `seeds` to `out`, each also reflowed, and returns
    them."""
    out.mkdir(parents=True, exist_ok=True)
    programs = []
    for seed in seeds:
        source = Gen(seed).program().program
        flowed = reflow(Text.of(source), random.Random(seed))
        path = out / program_file(seed)
        programs += [Program(path, source),
                     Program(path.with_stem(path.stem + "_reflowed"), flowed, reflowed=True)]
    for p in programs:
        p.path.write_text(p.source)
    return programs


def rejected_reflows(programs: list[Program]) -> list[str]:
    """Returns a line for each reflowed program that Fe0's native CLI does not compile."""
    cli_check.build()
    out = []
    for p in programs:
        if p.reflowed:
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
    programs = corpus() + generated(seeds_from(Seed(1), args.seeds), ROOT / "out/newline-check")
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
