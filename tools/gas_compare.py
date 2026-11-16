#!/usr/bin/env python3
"""Compare the gas that Fe0's output and Fe's output use for the same calls.

Each corpus program is compiled three ways: by Fe0's native CLI, and by Fe at -O 1 and at -O s.
All three builds are deployed on a local anvil node, and each gets the calls of the program's
call script (embed.py) and of fegen.DISPATCH. DESIGN.md §10, "On a node", says how the builds
deploy the programs they call. The gas of a call counts only what the contract's code spends.

The report gives, for each program, the gas of all its calls together for each build, and Fe0's
gas as a ratio of Fe's. With --calls, it also lists each call.

usage: gas_compare.py [--calls] [PROGRAM.fe ...]
"""
import argparse
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

import cli_check
import node
from node import Build, Compiled, Entry, Gas, Label, Node, Session


class CallGas(NamedTuple):
    """The gas each build's code spent on one call."""

    label: Label
    gas: dict[Build, Gas]


class ProgramGas(NamedTuple):
    """The gas each build spent on one program's calls."""

    name: str
    calls: list[CallGas]

    def total(self, build: Build) -> Gas:
        """Returns the gas of all the calls of `build`."""
        return Gas(sum(c.gas[build] for c in self.calls))


class Measured(NamedTuple):
    """What one build's code did on one call."""

    gas: Gas
    success: bool


def measure(n: Node, path: Path) -> ProgramGas:
    """Deploys each build of the program at `path` and sends it the calls of its call script.
    Errors with RuntimeError when a build does not deploy, and as node.Compiled.load does."""
    compiled = Compiled.load(path, Build)
    entries = compiled.calls()
    columns = []
    for b in Build:
        with n.session(compiled, b) as s:
            columns.append(_measure_build(s, entries))
    out = []
    for entry, measured in zip(entries, zip(*columns, strict=True), strict=True):
        if _disagree(measured):
            print(f"warning: {path.name} {entry.label}: the builds disagree on success",
                  file=sys.stderr)
        out.append(CallGas(entry.label, {b: m.gas for b, m in zip(Build, measured, strict=True)}))
    return ProgramGas(compiled.program.path.stem, out)


def _measure_build(s: Session, entries: list[Entry]) -> list[Measured]:
    """Deploys the build of `s` and returns what its code did on each of `entries`. Errors as
    Session.deploy_all and Session.call do."""
    s.deploy_all()
    # All the calls go first, so that the sends of code_gas do not run between them.
    runs = [s.call(e.message) for e in entries]
    return [Measured(s.code_gas(e.message, r), r.effects.success)
            for e, r in zip(entries, runs, strict=True)]


def _disagree(measured: Iterable[Measured]) -> bool:
    """Returns whether some builds succeeded on a call and others failed."""
    return len({m.success for m in measured}) > 1


def ratio(a: int, b: int) -> str:
    """Returns a / b with two decimals, or a dash when b is 0."""
    return f"{a / b:.2f}" if b else "-"


def line(name: str, cells: Iterable[object], ratios: Iterable[str]) -> str:
    """Returns one line of the report: a name, a cell per build and a ratio per Fe build."""
    return (f"{name:<16}" + "".join(f"{c:>10}" for c in cells)
            + "".join(f"{r:>7}" for r in ratios))


def row(name: str, gas: dict[Build, Gas]) -> str:
    """Returns the line of the gas of each build and Fe0's ratio to each Fe build."""
    return line(name, (gas[b] for b in Build), (ratio(gas[Build.FE0], gas[b]) for b in Build.fe()))


def report(results: list[ProgramGas], show_calls: bool) -> None:
    print(line("program", (b.label for b in Build), (f"/O{b.level}" for b in Build.fe())))
    for p in results:
        print(row(p.name, {b: p.total(b) for b in Build}))
        if show_calls:
            for c in p.calls:
                print(row(f"  {c.label}", c.gas))
    print(row("all", {b: Gas(sum(p.total(b) for p in results)) for b in Build}))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--calls", action="store_true", help="list each call")
    ap.add_argument("programs", nargs="*", type=Path, help="the programs (default: the corpus)")
    args = ap.parse_args()
    programs = node.programs(args.programs, node.corpus())
    cli_check.build()
    with Node() as n:
        results = []
        for p in programs:
            try:
                results.append(measure(n, p))
            except node.PROGRAM_ERRORS as e:
                print(f"skipped {p.name}: {e}", file=sys.stderr)
        report(results, args.calls)


if __name__ == "__main__":
    main()
