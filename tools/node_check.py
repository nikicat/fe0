#!/usr/bin/env python3
"""Check Fe0 against Fe on a node: the second differential harness of ADR 0016, step 0.

DESIGN.md §10, "On a node", says why it exists. It deploys Fe0's build and Fe's build of each
program of the corpus and of corpus/gen/ (tools/gen.py) on a local anvil node (node.py), and
sends the program's call script. DESIGN.md §10 says how the builds deploy the programs they
call. For each deployment and call, the two builds must agree on:

- whether it succeeded;
- the return data of a call, and the revert data of a failure;
- the logs, by topics and data;
- the storage slots it changed in each contract that the call script named, and their new
  words.

Fe builds at its reference level (SPEC.md, the subset rule) unless -O names another. The exit
status is 1 when Fe0's build of any program differs from Fe's build at that level.

With --levels, it also runs Fe's builds at its other levels, and compares each with Fe's build
at the level that -O names. A difference among Fe's builds is a bug in Fe (SPEC.md, the subset
rule). It is listed under its own heading and does not change the exit status. A build or
deployment that fails at only one of Fe's levels counts as such a difference.

usage: node_check.py [-O LEVEL] [--levels] [PROGRAM.fe ...]
"""
import argparse
import sys
from pathlib import Path
from typing import NamedTuple

import cli_check
import node
from embed import ProgramFile
from fegen import THIS
from node import Build, Compiled, Label, Node, Outcome, Session, line_label

# The label of each field of node.Effects, in the fields' order.
LABELS: tuple[str, ...] = ("success", "return or revert data", "logs", "storage writes")


class Difference(NamedTuple):
    """One line of a report."""

    program: ProgramFile
    # The deployment or call that differs, or the build that failed; None when the text
    # names its own place.
    place: Label | Build | None
    text: str

    def __str__(self) -> str:
        if self.place is None:
            return f"{self.program}: {self.text}"
        place = self.place.label if isinstance(self.place, Build) else self.place
        return f"{self.program} {place}: {self.text}"


def program_file(path: Path) -> ProgramFile:
    return ProgramFile(path.name)


def _show(value: object) -> str:
    """Returns a short text of a compared value."""
    text = "0x" + value.hex() if isinstance(value, bytes) else repr(value)
    return text if len(text) <= 400 else text[:397] + "..."


class BuildTrace(NamedTuple):
    """What one build did for each entry of a call script that it ran."""

    build: Build
    outcomes: list[Outcome]
    # Why the build stopped before the end of the script, or None when it ran to the end.
    failure: str | None


def trace(s: Session) -> BuildTrace:
    """Runs the call script of the program of `s` on its build, and returns what each
    deployment and call did. When a deployment that the script needs fails, it stops there.
    Errors as Session.call does."""
    out: list[Outcome] = []
    try:
        s.deploy_all(out.append)
    except RuntimeError as e:
        return BuildTrace(s.build, out, str(e))
    for case in s.compiled.program.diff.cases.deploys:
        out.append(Outcome(line_label(case), s.deploy(case, THIS).effects))
    for entry in s.compiled.calls():
        out.append(Outcome(entry.label, s.call(entry.message).effects))
    return BuildTrace(s.build, out, None)


class Report(NamedTuple):
    """The differences that one program shows."""

    # Between Fe0's build and Fe's build at the level that -O names.
    fe0: list[Difference]
    # Between that build of Fe's and its builds at other levels.
    fe: list[Difference]


def compare(name: ProgramFile, a: BuildTrace, b: BuildTrace) -> list[Difference]:
    """Returns each field that differs between the traces `a` and `b` of the program `name`,
    up to where the shorter one stops."""
    x, y = a.build.label, b.build.label
    return [Difference(name, u.label, f"{field}: {x} {_show(e)}, {y} {_show(f)}")
            for u, v in zip(a.outcomes, b.outcomes)
            for field, e, f in zip(LABELS, u.effects, v.effects, strict=True) if e != f]


class Checker(NamedTuple):
    """Checks programs on one node against one of Fe's builds."""

    n: Node
    # Fe's build at the level that -O names.
    against: Build
    # Fe's builds that --levels adds.
    others: list[Build]

    def check(self, path: Path) -> Report:
        """Runs the call script of the program at `path` on Fe0's build, on `against` and on
        each other build, and returns the differences. Errors as Session.call and
        Compiled.load do for Fe0's build and `against`. A failure of another
        build is reported as a difference, not raised."""
        name = program_file(path)
        compiled = Compiled.load(path, (Build.FE0, self.against))
        with self.n.session(compiled, Build.FE0) as s:
            ours = trace(s)
        with self.n.session(compiled, self.against) as s:
            theirs = trace(s)
        out = compare(name, ours, theirs)
        if failure := ours.failure or theirs.failure:
            out.append(Difference(name, None, failure))
        return Report(out, [d for b in self.others for d in self._check_build(path, theirs, b)])

    def _check_build(self, path: Path, theirs: BuildTrace, build: Build) -> list[Difference]:
        """Runs the call script of the program at `path` on `build`, and returns each
        difference from the trace `theirs`. A build that fails is a difference, not an
        error."""
        name = program_file(path)
        try:
            compiled = Compiled.load(path, (build,))
            with self.n.session(compiled, build) as s:
                other = trace(s)
        except node.PROGRAM_ERRORS as e:
            return [Difference(name, build, str(e))]
        out = compare(name, theirs, other)
        if (theirs.failure is None) != (other.failure is None):
            out.append(Difference(name, None, str(theirs.failure or other.failure)))
        return out

    def print_fe_bugs(self, fe_bugs: list[Difference]) -> None:
        """Prints how many differences Fe's other builds show, and lists them. Prints nothing
        when there are no other builds."""
        if not self.others:
            return
        builds = ", ".join(b.label for b in self.others)
        print(f"Fe's builds at {builds} against {self.against.label}: "
              f"{len(fe_bugs)} differences")
        if fe_bugs:
            print("Fe's own builds differ, a bug in Fe that does not change the exit status:")
            for d in fe_bugs:
                print(f"  {d}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    levels = ", ".join(str(b.level) for b in Build.fe())
    default = Build.reference()
    ap.add_argument("-O", dest="against", type=Build, choices=Build.fe(),
                    default=default, metavar="LEVEL",
                    help=f"Fe's optimization level: {levels} (default {default.level})")
    ap.add_argument("--levels", action="store_true",
                    help="also compare Fe's other levels with the level that -O names")
    ap.add_argument("programs", nargs="*", type=Path,
                    help="the programs (default: the corpus and corpus/gen/)")
    args = ap.parse_args()
    against: Build = args.against
    others = [b for b in Build.fe() if b != against] if args.levels else []
    programs = node.programs(args.programs, [*node.corpus(), *node.generated()])
    cli_check.build()
    failed = 0
    fe_bugs: list[Difference] = []
    with Node() as n:
        checker = Checker(n, against, others)
        for p in programs:
            try:
                report = checker.check(p)
            except node.PROGRAM_ERRORS as e:
                report = Report([Difference(program_file(p), None, str(e))], [])
            for d in report.fe0:
                print(d)
            failed += bool(report.fe0)
            fe_bugs += report.fe
    print(f"{len(programs)} programs on a node against {against.label}: {failed} differ")
    checker.print_fe_bugs(fe_bugs)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
