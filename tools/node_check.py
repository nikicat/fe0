#!/usr/bin/env python3
"""Check Fe0 against Fe on a node: the second differential harness of ADR 0016, step 0.

DESIGN.md §10, "On a node", says why it exists. It deploys Fe0's build and Fe's build of each
program of the corpus and of corpus/gen/ (tools/gen.py) on a local anvil node (node.py), and
sends the program's call script. For each deployment and call, the two builds must agree on:

- whether it succeeded;
- the return data of a call, and the revert data of a failure;
- the logs, by topics and data;
- the storage slots it changed, and their new words.

Fe builds at -O 1 unless -O says otherwise. The exit status is 1 when any program differs.

usage: node_check.py [-O LEVEL] [PROGRAM.fe ...]
"""
import argparse
import sys
from pathlib import Path

import cli_check
import node
from node import Build, Compiled, Deployment, Effects, Entry, Node

# The label of each field of node.Effects, in the fields' order.
LABELS: tuple[str, ...] = ("success", "return or revert data", "logs", "storage writes")


def differences(ours: Effects, theirs: Effects) -> list[str]:
    """Returns what differs between Fe0's effects and Fe's, one line per differing field."""
    return [f"{label}: Fe0 {_show(a)}, Fe {_show(b)}"
            for label, a, b in zip(LABELS, ours, theirs, strict=True) if a != b]


def _show(value: object) -> str:
    """Returns a short text of a compared value."""
    text = "0x" + value.hex() if isinstance(value, bytes) else repr(value)
    return text if len(text) <= 400 else text[:397] + "..."


def check(n: Node, path: Path, reference: Build) -> list[str]:
    """Runs the call script of the program at `path` on Fe0's build and on `reference`, and
    returns a line for each difference. Errors as Node.call and node.Compiled.load do."""
    compiled = Compiled.load(path, (Build.FE0, reference))
    name = compiled.program.path.name
    out: list[str] = []

    def compare(where: str, effects: dict[Build, Effects]) -> None:
        out.extend(f"{name} {where}: {d}"
                   for d in differences(effects[Build.FE0], effects[reference]))

    def compare_deployments(where: str, deployments: dict[Build, Deployment]) -> None:
        compare(where, {b: d.effects for b, d in deployments.items()})

    mains = compiled.deploy_main(n)
    compare_deployments(f"{Entry.line(compiled.program.diff.cases.main).label} (main deployment)",
                        mains)
    try:
        addresses = node.addresses(mains)
    except RuntimeError as e:
        return [*out, f"{name}: {e}"]
    for case in compiled.program.diff.cases.deploys:
        compare_deployments(Entry.line(case).label, compiled.deploy(n, case))
    for entry in compiled.calls():
        compare(entry.label, {b: n.call(a, entry.case).effects for b, a in addresses.items()})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    levels = ", ".join(str(b.level) for b in Build.fe())
    ap.add_argument("-O", dest="reference", type=Build, choices=Build.fe(), default=Build.FE_O1,
                    metavar="LEVEL",
                    help=f"Fe's optimization level: {levels} (default {Build.FE_O1.level})")
    ap.add_argument("programs", nargs="*", type=Path,
                    help="the programs (default: the corpus and corpus/gen/)")
    args = ap.parse_args()
    reference: Build = args.reference
    programs = node.programs(args.programs, [*node.corpus(), *node.generated()])
    cli_check.build()
    failed = 0
    with Node() as n:
        for p in programs:
            try:
                diffs = check(n, p, reference)
            except node.PROGRAM_ERRORS as e:
                diffs = [f"{p.name}: {e}"]
            for d in diffs:
                print(d)
            failed += bool(diffs)
    print(f"{len(programs)} programs on a node against {reference.label}: {failed} differ")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
