#!/usr/bin/env python3
"""Compare the gas that Fe0's output and Fe's output use for the same calls.

Each corpus program is compiled three ways: by Fe0's native CLI, and by Fe at -O 1 and at
-O s. All three builds are deployed on a local anvil node, and each gets the calls of the
program's call script (embed.py) and of fegen.DISPATCH. The gas of a call is the receipt's
gasUsed less the gas of the same transaction sent to an account with no code. So it counts only
what the contract's code spends.

The report gives, for each program, the gas of all its calls together for each build, and Fe0's
gas as a ratio of Fe's. With --calls, it also lists each call.

usage: gas_compare.py [--calls] [PROGRAM.fe ...]
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
from enum import Enum
from pathlib import Path
from typing import NamedTuple, NewType

import cli_check
import embed
from fegen import DISPATCH, FE, ROOT, FeName, FeSource, Payload

# The node's hardfork. Cancun has no calldata floor price (EIP-7623), so the gas of a call less
# the gas of the same transaction to an account with no code is what the code spent.
HARDFORK: str = "cancun"
PORT: int = 8645
URL: str = f"http://127.0.0.1:{PORT}"
# The gas limit of each transaction: the harness's CALL_GAS (fe0/src/difftest.fe) and more.
TX_GAS: int = 30_000_000
# An address with no code, which gives the gas of a transaction without execution.
NO_CODE: str = "0x000000000000000000000000000000000000dEaD"
OUT: Path = ROOT / "out/gas"

# The gas that a contract's code spends on one call or deployment.
Gas = NewType("Gas", int)
Address = NewType("Address", str)


class Build(Enum):
    """A compiler and its options."""

    FE0 = "Fe0"
    FE_O1 = "Fe -O 1"
    FE_OS = "Fe -O s"


class Node:
    """A running anvil node and its first funded account."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen(["anvil", "--port", str(PORT), "--hardfork", HARDFORK,
                                      "--gas-limit", str(TX_GAS * 2), "--silent"])
        for _ in range(100):
            try:
                accounts = self.rpc("eth_accounts")
                assert isinstance(accounts, list)
                self.sender: str = accounts[0]
                return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("anvil did not start")

    def rpc(self, method: str, *params: object) -> object:
        """Returns the result of a JSON-RPC call. Errors with RuntimeError on an RPC error."""
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        req = urllib.request.Request(URL, body.encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            reply = json.load(r)
        if "error" in reply:
            raise RuntimeError(f"{method}: {reply['error']}")
        return reply["result"]

    def send(self, to: Address | None, data: bytes, value: int) -> dict[str, str]:
        """Sends a transaction and returns its receipt."""
        tx = {"from": self.sender, "data": "0x" + data.hex(), "value": hex(value),
              "gas": hex(TX_GAS)}
        if to is not None:
            tx["to"] = to
        h = self.rpc("eth_sendTransaction", tx)
        for _ in range(1000):
            receipt = self.rpc("eth_getTransactionReceipt", h)
            if isinstance(receipt, dict):
                return receipt
            time.sleep(0.005)
        raise RuntimeError(f"no receipt for {h}")

    def gas(self, to: Address | None, data: bytes, value: int) -> tuple[Gas, bool, dict[str, str]]:
        """Returns the gas that the code spends on a transaction, whether it succeeded, and its
        receipt."""
        receipt = self.send(to, data, value)
        base = int(self.send(Address(NO_CODE), data, value)["gasUsed"], 16)
        if to is None:
            # A create also pays 32,000 for the new account (EIP-2) and 2 per 32 bytes of
            # initcode (EIP-3860), which a transaction to NO_CODE does not.
            base += 32_000 + 2 * ((len(data) + 31) // 32)
        return Gas(int(receipt["gasUsed"], 16) - base), receipt["status"] == "0x1", receipt

    def close(self) -> None:
        self.proc.terminate()
        self.proc.wait()


def contract_name(source: FeSource) -> FeName:
    """Returns the name of the program's contract."""
    m = embed.CONTRACT.search(source)
    if m is None:
        raise ValueError("no contract")
    return FeName(m[1])


def initcode(build: Build, program: Path, source: FeSource) -> bytes:
    """Returns the deployment code of `program` from `build`. Errors with RuntimeError when the
    compiler fails."""
    if build is Build.FE0:
        run = cli_check.Run.of(program, source)
        if not run.compiled():
            raise RuntimeError(f"Fe0 rejects {program}: {run.stderr.strip()}")
        return bytes.fromhex(run.stdout.strip())
    out = OUT / program.stem / build.name
    level = "1" if build is Build.FE_O1 else "s"
    r = subprocess.run([FE, "build", "-O", level, str(program), "--out-dir", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"fe build {program}: {r.stderr.strip()}")
    return bytes.fromhex((out / f"{contract_name(source)}.bin").read_text().strip())


class CallGas(NamedTuple):
    """The gas each build's code spent on one call."""

    line: str
    gas: dict[Build, Gas]


class ProgramGas(NamedTuple):
    """The gas each build spent on one program's deployment and calls."""

    name: str
    deploy: dict[Build, Gas]
    calls: list[CallGas]

    def total(self, build: Build) -> Gas:
        """Returns the gas of all the calls of `build`."""
        return Gas(sum(c.gas[build] for c in self.calls))


def measure(node: Node, program: Path) -> ProgramGas:
    """Deploys each build of `program` and sends it the calls of its call script."""
    source = FeSource(program.read_text())
    cases = embed.parse_calls(embed.calls_path(program), embed.selectors(source))
    deploy: dict[Build, Gas] = {}
    addresses: dict[Build, Address] = {}
    for build in Build:
        main: Payload = cases.main.payload
        gas, ok, receipt = node.gas(None, initcode(build, program, source) + main.encode(),
                                    main.value)
        if not ok:
            raise RuntimeError(f"{build.value} build of {program.name} did not deploy")
        deploy[build] = gas
        addresses[build] = Address(receipt["contractAddress"])
    payloads = [(f"line {c.number}", c.payload) for c in cases.calls]
    payloads += [(f"dispatch {i}", p) for i, p in enumerate(DISPATCH, start=1)]
    calls = []
    for line, payload in payloads:
        results = {b: node.gas(addresses[b], payload.encode(), payload.value) for b in Build}
        if len({ok for _, ok, _ in results.values()}) > 1:
            print(f"warning: {program.name} {line}: the builds disagree on success", file=sys.stderr)
        calls.append(CallGas(line, {b: g for b, (g, _, _) in results.items()}))
    return ProgramGas(program.stem, deploy, calls)


def ratio(a: int, b: int) -> str:
    return f"{a / b:.2f}" if b else "-"


def report(results: list[ProgramGas], show_calls: bool) -> None:
    head = f"{'program':<16}" + "".join(f"{b.value:>10}" for b in Build) + f"{'/O1':>7}{'/Os':>7}"
    print(head)
    for p in results:
        t = {b: p.total(b) for b in Build}
        print(f"{p.name:<16}" + "".join(f"{t[b]:>10}" for b in Build)
              + f"{ratio(t[Build.FE0], t[Build.FE_O1]):>7}{ratio(t[Build.FE0], t[Build.FE_OS]):>7}")
        if show_calls:
            for c in p.calls:
                print(f"  {c.line:<14}" + "".join(f"{c.gas[b]:>10}" for b in Build)
                      + f"{ratio(c.gas[Build.FE0], c.gas[Build.FE_O1]):>7}"
                      + f"{ratio(c.gas[Build.FE0], c.gas[Build.FE_OS]):>7}")
    total = {b: sum(p.total(b) for p in results) for b in Build}
    print(f"{'all':<16}" + "".join(f"{total[b]:>10}" for b in Build)
          + f"{ratio(total[Build.FE0], total[Build.FE_O1]):>7}"
          + f"{ratio(total[Build.FE0], total[Build.FE_OS]):>7}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--calls", action="store_true", help="list each call")
    ap.add_argument("programs", nargs="*", type=Path, help="the programs (default: the corpus)")
    args = ap.parse_args()
    programs = args.programs or sorted((ROOT / "corpus").glob("*.fe"))
    cli_check.build()
    node = Node()
    try:
        results = []
        for p in programs:
            try:
                results.append(measure(node, p.resolve()))
            except RuntimeError as e:
                print(f"skipped {p.name}: {e}", file=sys.stderr)
        report(results, args.calls)
    finally:
        node.close()


if __name__ == "__main__":
    main()
