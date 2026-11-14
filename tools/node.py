"""Deploy and call Fe0's and Fe's builds of a corpus program on a local anvil node.

It sends a program's call script and fegen.DISPATCH to each build, and reports what each
transaction did and the gas that a call's code spent. When the call script deploys other
programs for the program to call, each build deploys its own build of them.

Each build runs the whole script from the same state of the node (`Node.isolated`). So both
builds send the same transactions from the same accounts at the same nonces, and their
deployments get the same addresses: a word that holds one, such as a map slot hashed from it,
is the same in both builds.
"""
import subprocess
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, NamedTuple, NewType, Self, cast

from eth_typing import ChecksumAddress
from hexbytes import HexBytes
from web3 import HTTPProvider, Web3
from web3.types import (CallTrace, DiffModeTrace, RPCEndpoint, TraceConfig, TraceData, TxParams,
                        TxReceipt, Wei)

import cli_check
import embed
import gen
from fegen import (DISPATCH, FE, ROOT, THIS, Account, AccountIndex, AddressArg, Case,
                   DeploymentName, Payload, Word)

# The node's hardfork. Cancun has no calldata floor price (EIP-7623), so the gas of a call less
# the gas of the same transaction to an account with no code is what the code spent.
HARDFORK: str = "cancun"
PORT: int = 8645
URL: str = f"http://127.0.0.1:{PORT}"
# How long anvil may take to answer after it starts, in seconds.
START_TIMEOUT: float = 10
# An address with no code, which gives the gas of a transaction without execution.
NO_CODE: ChecksumAddress = Web3.to_checksum_address("0x000000000000000000000000000000000000dead")
OUT: Path = ROOT / "out/node"
# The errors of loading, compiling and running one program.
PROGRAM_ERRORS = (RuntimeError, embed.ScriptError, OSError)

# An amount of gas.
Gas = NewType("Gas", int)
# The gas limit of each transaction: the in-EVM harness's CALL_GAS (fe0/src/difftest.fe) and more.
TX_GAS: Gas = Gas(30_000_000)
# The gas limit of a block on the node.
BLOCK_GAS: Gas = Gas(2 * TX_GAS)
# A storage slot and a word, as the node prints them: 0x and 64 hex digits.
Slot = NewType("Slot", str)
StorageWord = NewType("StorageWord", str)
ZERO_WORD: StorageWord = StorageWord("0x" + "0" * 64)
# A contract's storage, or the slots of it that a transaction changed.
Storage = dict[Slot, StorageWord]
# One build's deployments, by name.
Addresses = dict[DeploymentName, ChecksumAddress]


class Build(Enum):
    """A compiler and its options."""

    _value_: Literal["1", "s"] | None
    FE0 = None
    FE_O1 = "1"
    FE_OS = "s"

    @property
    def level(self) -> Literal["1", "s"] | None:
        """Fe's optimization level, or None for Fe0's build."""
        return self._value_

    @property
    def label(self) -> str:
        """The build's name in reports, such as "Fe -O 1"."""
        return "Fe0" if self.level is None else f"Fe -O {self.level}"

    @classmethod
    def fe(cls) -> list[Build]:
        """Returns Fe's builds, one per optimization level."""
        return [b for b in cls if b.level is not None]

    def initcode(self, program: embed.Program) -> bytes:
        """Returns the deployment code of `program`. Errors with RuntimeError when the compiler
        fails."""
        if self.level is None:
            run = cli_check.Run.of(program.path, program.diff.source)
            if not run.compiled():
                raise RuntimeError(f"Fe0 rejects {program.path.name}: {run.stderr.strip()}")
            return bytes.fromhex(run.stdout.strip())
        out = OUT / program.path.stem / self.name
        r = subprocess.run([FE, "build", "-O", self.level, str(ROOT / program.path),
                            "--out-dir", str(out)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"fe build {program.path.name}: {r.stderr.strip()}")
        return bytes.fromhex((out / f"{program.diff.contract}.bin").read_text().strip())


def programs(paths: list[Path], default: Iterable[Path]) -> list[Path]:
    """Returns `paths` as absolute paths, or `default`, sorted, when there are none."""
    return [p.resolve() for p in paths] or sorted(default)


def corpus() -> list[Path]:
    """Returns the hand-written programs of the corpus."""
    return list(embed.CORPUS.glob("*.fe"))


def generated() -> list[Path]:
    """Returns the programs that tools/gen.py wrote."""
    return list(gen.GEN.glob("*.fe"))


class Log(NamedTuple):
    """A log, without the address of the contract that emitted it."""

    topics: tuple[HexBytes, ...]
    data: HexBytes


class Effects(NamedTuple):
    """The part of what a transaction did that two builds of a program must agree on."""

    success: bool
    # The return data of a call that succeeds, and the revert data of any transaction that fails.
    output: bytes
    logs: tuple[Log, ...]
    # The storage slots that changed, with their new words, of each deployment of the build by
    # name: the program's own, the callees', and the one that the transaction created. A slot
    # that was cleared maps to the zero word.
    storage: dict[DeploymentName, Storage]


class Run(NamedTuple):
    """What one call did."""

    effects: Effects
    # The gas of the whole transaction.
    gas_used: Gas


class Deployment(NamedTuple):
    """What one deployment did."""

    effects: Effects
    # The created contract, or None when the deployment failed.
    address: ChecksumAddress | None


class Entry(NamedTuple):
    """A deployment or call, with the label that reports name it by."""

    label: str
    case: Case

    @classmethod
    def line(cls, case: Case) -> Self:
        """Returns the entry of `case`, a line of the call script."""
        return cls(f"line {case.number}", case)

    @classmethod
    def deployment(cls, case: Case, name: DeploymentName) -> Self:
        """Returns the entry of `case`, the call script's line that deploys `name`, such as
        "line 3 (t0)" or "line 1 (main deployment)"."""
        what = "main deployment" if name == THIS else name
        return cls(f"line {case.number} ({what})", case)


class Outcome(NamedTuple):
    """What one entry did, by the entry's label."""

    label: str
    effects: Effects


class Node:
    """A running anvil node and its funded accounts. It stops the node on exit."""

    def __init__(self) -> None:
        """Starts anvil. Errors with RuntimeError when another process serves PORT, or when
        anvil exits or does not answer within START_TIMEOUT."""
        # Without retries, a request to a node that is not up yet fails at once.
        self.w3 = Web3(HTTPProvider(URL, exception_retry_configuration=None))
        if self.w3.is_connected():
            raise RuntimeError(f"another process serves port {PORT}")
        self.proc = subprocess.Popen(["anvil", "--port", str(PORT), "--hardfork", HARDFORK,
                                      "--gas-limit", str(BLOCK_GAS), "--silent"])
        try:
            self._await_start()
            self.accounts: tuple[ChecksumAddress, ...] = tuple(self.w3.eth.accounts)
        except BaseException:
            self._stop()
            raise

    @contextmanager
    def isolated(self) -> Iterator[None]:
        """Runs the body from the node's current state, and puts that state back after it.
        Errors with RuntimeError when the node takes no snapshot, or does not go back to it."""
        reply = self.w3.provider.make_request(RPCEndpoint("evm_snapshot"), [])
        if "result" not in reply:
            raise RuntimeError(f"the node takes no snapshot: {reply.get('error')}")
        snapshot = reply["result"]
        try:
            yield
        finally:
            reverted = self.w3.provider.make_request(RPCEndpoint("evm_revert"), [snapshot])
        if reverted.get("result") is not True:
            raise RuntimeError(f"the node does not revert its snapshot: {reverted.get('error')}")

    def _await_start(self) -> None:
        deadline = time.monotonic() + START_TIMEOUT
        while not self.w3.is_connected():
            if (code := self.proc.poll()) is not None:
                raise RuntimeError(f"anvil exited with status {code}")
            if time.monotonic() > deadline:
                raise RuntimeError(f"anvil did not answer within {START_TIMEOUT} s")
            time.sleep(0.1)

    def _stop(self) -> None:
        self.proc.terminate()
        self.proc.wait()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self._stop()

    def create(self, initcode: bytes, case: Case, book: Addresses,
               name: DeploymentName) -> Deployment:
        """Deploys `initcode` with the constructor arguments, value and sender of `case`, as
        the deployment `name` of the build whose other deployments are `book`. Errors as _send
        and _encode do."""
        receipt = self._send(case, {"data": initcode + self._encode(case.payload, book)})
        address = receipt["contractAddress"] if receipt["status"] else None
        # A deployment that succeeds outputs its runtime code, which differs between builds.
        output = b"" if address else self._output(receipt)
        effects = self._effects(receipt, output, {**book, name: address} if address else book)
        return Deployment(effects, address)

    def call(self, case: Case, book: Addresses) -> Run:
        """Sends the payload of `case` to its deployment in `book`, a build's deployments.
        Errors as _send and _encode do."""
        receipt = self._send(case, {"to": book[case.to], "data": self._encode(case.payload, book)})
        return Run(self._effects(receipt, self._output(receipt), book), Gas(receipt["gasUsed"]))

    def code_gas(self, case: Case, run: Run, book: Addresses) -> Gas:
        """Returns the gas that the code spent on `run`, a call that sent `case` with `book`."""
        base = self._send(case, {"to": NO_CODE, "data": self._encode(case.payload, book)})
        return Gas(run.gas_used - base["gasUsed"])

    def _account(self, index: AccountIndex) -> ChecksumAddress:
        """Returns the account at `index`. Errors with RuntimeError when the node has none."""
        if not 0 <= index < len(self.accounts):
            raise RuntimeError(f"the node has no account {index}")
        return self.accounts[index]

    def _encode(self, payload: Payload, book: Addresses) -> bytes:
        """Returns the bytes of `payload`, with the address of each account and deployment it
        names. `book` holds the deployments. Errors as _account does, and with RuntimeError when
        `book` lacks a deployment."""
        def address(a: AddressArg) -> Word:
            if isinstance(a, Account):
                return _word(self._account(a.index))
            if a.name not in book:
                raise RuntimeError(f"{a} names no deployment of this build")
            return _word(book[a.name])
        return payload.encode(address)

    def transact(self, tx: TxParams) -> TxReceipt:
        """Sends `tx`, from account 0 with TX_GAS unless `tx` sets them, and returns the receipt.
        Errors with RuntimeError when the transaction fails."""
        receipt = self._receipt({"from": self.accounts[0], "gas": TX_GAS, **tx})
        if not receipt["status"]:
            raise RuntimeError(f"the transaction {receipt['transactionHash'].to_0x_hex()} failed")
        return receipt

    def _send(self, case: Case, tx: TxParams) -> TxReceipt:
        """Sends `tx` with the value of `case` from its sender, and returns the receipt. Errors
        as _account does."""
        return self._receipt({**tx, "from": self._account(case.sender),
                              "value": Wei(case.payload.value), "gas": TX_GAS})

    def _receipt(self, tx: TxParams) -> TxReceipt:
        """Sends `tx` and returns its receipt, whether or not the transaction succeeds."""
        return self.w3.eth.wait_for_transaction_receipt(self.w3.eth.send_transaction(tx))

    def _effects(self, receipt: TxReceipt, output: bytes, book: Addresses) -> Effects:
        """Returns what the transaction of `receipt` did, with the storage of `book`."""
        success = receipt["status"] == 1
        storage = self._storage_diff(receipt, book) if success else {}
        logs = tuple(Log(tuple(e["topics"]), e["data"]) for e in receipt["logs"])
        return Effects(success, output, logs, storage)

    def _output(self, receipt: TxReceipt) -> bytes:
        """Returns the return or revert data of the transaction of `receipt`."""
        trace = cast(CallTrace, self.w3.geth.debug.trace_transaction(
            receipt["transactionHash"], TraceConfig(tracer="callTracer")))
        return bytes(trace.get("output", b""))

    def _storage_diff(self, receipt: TxReceipt, book: Addresses) -> dict[DeploymentName, Storage]:
        """Returns the storage slots of each deployment of `book` that the transaction of
        `receipt` changed, leaving out the deployments with none."""
        diff = cast(DiffModeTrace, self.w3.geth.debug.trace_transaction(
            receipt["transactionHash"],
            TraceConfig(tracer="prestateTracer", tracerConfig={"diffMode": True})))
        out = {}
        for name, address in book.items():
            pre, post = _storage(diff["pre"], address), _storage(diff["post"], address)
            if changed := {s: post.get(s, ZERO_WORD) for s in sorted(pre.keys() | post.keys())}:
                out[name] = changed
        return out


def _word(address: ChecksumAddress) -> Word:
    """Returns `address` as an ABI word."""
    return Word(int(address, 16))


def _storage(accounts: dict[ChecksumAddress, TraceData], account: ChecksumAddress) -> Storage:
    """Returns the storage of `account` in a prestate trace's map of accounts."""
    storage = accounts.get(account, TraceData()).get("storage", {})
    return {Slot(s): StorageWord(w) for s, w in storage.items()}


def _load_program(path: Path) -> embed.Program:
    """Loads the program at `path`, an absolute path. Errors with RuntimeError when the path is
    outside ROOT, and as embed.Program.load does."""
    if not path.is_relative_to(ROOT):
        raise RuntimeError(f"{path} is outside {ROOT}")
    return embed.Program.load(path)


@dataclass(frozen=True)
class Compiled:
    """A program with the deployment code of each of its builds, each compiled once, and the
    same for each callee of its call script."""

    program: embed.Program
    # The deployment code of each build, by deployment name: THIS for the program, and the
    # callee's name for each callee.
    initcode: dict[DeploymentName, dict[Build, bytes]]

    @classmethod
    def load(cls, path: Path, builds: Iterable[Build]) -> Self:
        """Loads the program at `path`, an absolute path under ROOT, and its callees, and
        compiles each build of each. Errors with RuntimeError when a build does not compile,
        and as _load_program does."""
        builds = list(builds)
        program = _load_program(path)

        def each_build(p: embed.Program) -> dict[Build, bytes]:
            return {b: b.initcode(p) for b in builds}
        initcode = {THIS: each_build(program)}
        for c in program.diff.cases.callees:
            initcode[c.name] = each_build(_load_program(c.program))
        return cls(program, initcode)

    def calls(self) -> list[Entry]:
        """Returns the calls to send to the main deployment: the call script's, then
        fegen.DISPATCH's."""
        script = [Entry.line(c) for c in self.program.diff.cases.calls]
        return script + [Entry(f"dispatch {i}", Case(0, p)) for i, p in enumerate(DISPATCH, 1)]


class Session:
    """One build's deployments of a compiled program and its callees on a node, by name."""

    def __init__(self, node: Node, compiled: Compiled, build: Build) -> None:
        self.node = node
        self.compiled = compiled
        self.build = build
        self.book: Addresses = {}

    def deploy(self, case: Case, name: DeploymentName) -> Deployment:
        """Deploys the build of the program that `name` names with `case`. Errors as
        Node.create does."""
        return self.node.create(self.compiled.initcode[name][self.build], case, self.book, name)

    def keep(self, name: DeploymentName, deployment: Deployment) -> None:
        """Records the contract that `deployment` created as the deployment `name`. Errors with
        RuntimeError when it created none."""
        if deployment.address is None:
            raise RuntimeError(f"the {self.build.label} build's deployment {name} failed")
        self.book[name] = deployment.address

    def deploy_all(self, record: Callable[[Outcome], object] = lambda _: None) -> None:
        """Deploys and keeps the callees, then the main deployment, and passes what each
        deployment did to `record` before it keeps it. Errors as `keep` does, and as
        Node.create does."""
        def deploy(name: DeploymentName, case: Case) -> None:
            d = self.deploy(case, name)
            record(Outcome(Entry.deployment(case, name).label, d.effects))
            self.keep(name, d)
        cases = self.compiled.program.diff.cases
        for callee in cases.callees:
            deploy(callee.name, callee.case)
        deploy(THIS, cases.main)

    def call(self, case: Case) -> Run:
        """Sends `case` to its deployment. Errors as Node.call does."""
        return self.node.call(case, self.book)
