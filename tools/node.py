"""Deploy and call Fe0's and Fe's builds of a corpus program on a local anvil node.

The differential harness on a node, step 0 of ADR 0016. It exists because inside `fe test` every
call comes from one sender and logs are not visible.
"""
import subprocess
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import NamedTuple, NewType, Self, cast

from eth_typing import ChecksumAddress
from hexbytes import HexBytes
from web3 import HTTPProvider, Web3
from web3.types import (CallTrace, DiffModeTrace, RPCEndpoint, TraceConfig, TraceData, TxParams,
                        TxReceipt, Wei)

import cli_check
import embed
import gen
from fegen import (DISPATCH, FE, NO_LINE, ROOT, THIS, Account, AccountIndex, AddressArg,
                   CallCase, Case, DeploymentName, Payload, Probe, ProbeIndex, Word,
                   script_place)

# The node's hardfork. Cancun has no calldata floor price (EIP-7623), so the gas of a call less
# the gas of the same transaction to an account with no code is what the code spent.
HARDFORK: str = "cancun"
PORT: int = 8645
URL: str = f"http://127.0.0.1:{PORT}"
# How long anvil may take to answer after it starts, in seconds.
START_TIMEOUT: float = 10
# An address with no code, which gives the gas of a transaction without execution.
NO_CODE: ChecksumAddress = Web3.to_checksum_address(
    "0x000000000000000000000000000000000000dead")
OUT: Path = ROOT / "out/node"
# The errors of loading, compiling and running one program.
PROGRAM_ERRORS = (RuntimeError, embed.ScriptError, OSError)

# An amount of gas.
Gas = NewType("Gas", int)
# The gas limit of each transaction: the in-EVM harness's CALL_GAS (fe0/src/difftest.fe) and
# more.
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

    _value_: embed.OptLevel | None
    FE0 = None
    FE_O0 = "0"
    FE_O1 = "1"
    FE_O2 = "2"
    FE_OS = "s"

    @property
    def level(self) -> embed.OptLevel | None:
        """Fe's optimization level, or None for Fe0's build."""
        return self._value_

    @property
    def label(self) -> str:
        """The build's name in reports, such as "Fe -O 1"."""
        return "Fe0" if self.level is None else f"Fe -O {self.level}"

    @classmethod
    def reference(cls) -> Build:
        """Returns Fe's reference build (embed.REFERENCE_LEVEL)."""
        return cls(embed.REFERENCE_LEVEL)

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
    # The return data of a call that succeeds, and the revert data of any transaction that
    # fails.
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


# A report names a deployment or call by its line in the call script or by its dispatcher
# probe, as the in-EVM harness does (DESIGN.md §10).
Label = NewType("Label", str)


def line_label(case: Case) -> Label:
    return Label(script_place(case.number))


def deployment_label(case: Case, name: DeploymentName) -> Label:
    if case.number == NO_LINE:
        return line_label(case)
    what = "main deployment" if name == THIS else name
    return Label(f"{line_label(case)} ({what})")


def dispatch_label(index: ProbeIndex) -> Label:
    """Returns the label of the call of fegen.DISPATCH at `index`, counted from 1, such as
    "dispatch 1"."""
    return Label(f"dispatch {index}")


class Message(NamedTuple):
    """A call names its target and its address arguments by deployment, as a call script does
    (ADR 0020). A build's addresses exist only after that build deploys."""

    payload: Payload
    sender: AccountIndex = AccountIndex(0)
    to: DeploymentName = THIS


class Entry(NamedTuple):
    label: Label
    message: Message

    @classmethod
    def line(cls, call: CallCase) -> Self:
        """Returns the entry of `call`, labelled by its line in the call script."""
        case = call.case
        return cls(line_label(case), Message(case.payload, case.sender, call.to))

    @classmethod
    def probe(cls, probe: Probe) -> Self:
        """Returns the entry of `probe`, which account 0 sends to the main deployment."""
        return cls(dispatch_label(probe.index), Message(probe.payload))


class Outcome(NamedTuple):
    label: Label
    effects: Effects


# The id of a snapshot of the node's state, as evm_snapshot returns it.
SnapshotId = NewType("SnapshotId", str)


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
        snapshot = self._snapshot()
        try:
            yield
        finally:
            self._revert(snapshot)

    def _snapshot(self) -> SnapshotId:
        """Takes a snapshot of the node's state. Errors with RuntimeError when the node takes
        none."""
        match reply := self.w3.provider.make_request(RPCEndpoint("evm_snapshot"), []):
            case {"result": str() as snapshot}:
                return SnapshotId(snapshot)
        raise RuntimeError(f"the node takes no snapshot: {reply.get('error')}")

    def _revert(self, snapshot: SnapshotId) -> None:
        """Puts back the node's state at `snapshot`. Errors with RuntimeError when the node does
        not go back to it."""
        match reply := self.w3.provider.make_request(RPCEndpoint("evm_revert"), [snapshot]):
            case {"result": True}:
                return
        raise RuntimeError(f"the node does not revert its snapshot: {reply.get('error')}")

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

    def account(self, index: AccountIndex) -> ChecksumAddress:
        """Returns the account at `index`. Errors with RuntimeError when the node has none."""
        if not 0 <= index < len(self.accounts):
            raise RuntimeError(f"the node has no account {index}")
        return self.accounts[index]

    def transact(self, tx: TxParams) -> TxReceipt:
        """Sends `tx`, from account 0 with TX_GAS unless `tx` sets them, and returns the
        receipt. Errors with RuntimeError when the transaction fails."""
        receipt = self.receipt({"from": self.accounts[0], "gas": TX_GAS, **tx})
        if not _succeeded(receipt):
            tx_hash = receipt['transactionHash'].to_0x_hex()
            raise RuntimeError(f"the transaction {tx_hash} failed")
        return receipt

    def receipt(self, tx: TxParams) -> TxReceipt:
        """Sends `tx` and returns its receipt, whether or not the transaction succeeds. To error
        on a failed transaction, use Node.transact."""
        return self.w3.eth.wait_for_transaction_receipt(self.w3.eth.send_transaction(tx))

    def output(self, receipt: TxReceipt) -> bytes:
        """Returns the return or revert data of the transaction of `receipt`."""
        trace = cast(CallTrace, self.w3.geth.debug.trace_transaction(
            receipt["transactionHash"], TraceConfig(tracer="callTracer")))
        return bytes(trace.get("output", b""))

    def state_diff(self, receipt: TxReceipt) -> DiffModeTrace:
        """Returns the accounts that the transaction of `receipt` changed, before and after."""
        return cast(DiffModeTrace, self.w3.geth.debug.trace_transaction(
            receipt["transactionHash"],
            TraceConfig(tracer="prestateTracer", tracerConfig={"diffMode": True})))

    @contextmanager
    def session(self, compiled: Compiled, build: Build) -> Iterator[Session]:
        """Yields a Session of `build` of `compiled` that starts from the node's state now, so
        that every build gets the same addresses (DESIGN.md §10, "On a node"). Errors as
        Node.isolated does."""
        with self.isolated():
            yield Session(self, compiled, build)


def _succeeded(receipt: TxReceipt) -> bool:
    """Returns whether the transaction of `receipt` succeeded."""
    return receipt["status"] == 1


def _word(address: ChecksumAddress) -> Word:
    """Returns `address` as an ABI word."""
    return Word(int(address, 16))


def _storage(accounts: dict[ChecksumAddress, TraceData], account: ChecksumAddress) -> Storage:
    """Returns the storage of `account` in a prestate trace's map of accounts."""
    storage = accounts.get(account, TraceData()).get("storage", {})
    return {Slot(s): StorageWord(w) for s, w in storage.items()}


def _changed_slots(pre: Storage, post: Storage) -> Storage:
    """Returns each slot of `pre` or `post` with its word in `post`, or the zero word when
    `post` lacks it. The two are one account's storage in a prestate trace in diff mode, which
    lists only the slots that the transaction changed."""
    return {s: post.get(s, ZERO_WORD) for s in sorted(pre.keys() | post.keys())}


def _load_program(path: Path) -> embed.Program:
    """Loads the program at `path`, an absolute path. Errors with RuntimeError when the path is
    outside ROOT, and as embed.Program.load does."""
    if not path.is_relative_to(ROOT):
        raise RuntimeError(f"{path} is outside {ROOT}")
    return embed.Program.load(path)


@dataclass(frozen=True)
class Compiled:
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
        """Returns the calls to send. The call script's come first, and each goes to the
        deployment it names. Then come fegen.DISPATCH's, which go to the main deployment."""
        return ([Entry.line(c) for c in self.program.diff.cases.calls]
                + [Entry.probe(p) for p in DISPATCH])


class Session:
    def __init__(self, node: Node, compiled: Compiled, build: Build) -> None:
        self.node = node
        self.compiled = compiled
        self.build = build
        self.book: Addresses = {}

    def deploy(self, case: Case, name: DeploymentName) -> Deployment:
        """Deploys the build of the program that `name` names, with the constructor arguments,
        value and sender of `case`. Errors as Node.account and Session.address do."""
        initcode = self.compiled.initcode[name][self.build]
        receipt = self._send(case.payload, case.sender,
                             {"data": initcode + self._encode(case.payload)})
        address = receipt["contractAddress"] if _succeeded(receipt) else None
        # A deployment that succeeds outputs its runtime code, which differs between builds.
        output = b"" if address else self.node.output(receipt)
        book = {**self.book, name: address} if address else self.book
        return Deployment(self._effects(receipt, output, book), address)

    def keep(self, name: DeploymentName, deployment: Deployment) -> None:
        """Records the contract that `deployment` created as the deployment `name`. Errors with
        RuntimeError when it created none."""
        if deployment.address is None:
            raise RuntimeError(f"the {self.build.label} build's deployment {name} failed")
        self.book[name] = deployment.address

    def deploy_all(self, record: Callable[[Outcome], object] = lambda _: None) -> None:
        """Deploys and keeps the callees, then the main deployment, and passes what each
        deployment did to `record` before it keeps it. Errors as `keep` and `deploy`
        do."""
        def deploy(name: DeploymentName, case: Case) -> None:
            d = self.deploy(case, name)
            record(Outcome(deployment_label(case, name), d.effects))
            self.keep(name, d)
        cases = self.compiled.program.diff.cases
        for callee in cases.callees:
            deploy(callee.name, callee.case)
        deploy(THIS, cases.main)

    def call(self, message: Message) -> Run:
        """Sends `message` to its deployment. Errors as Node.account and Session.address do."""
        tx: TxParams = {"to": self.address(message.to), "data": self._encode(message.payload)}
        receipt = self._send(message.payload, message.sender, tx)
        effects = self._effects(receipt, self.node.output(receipt), self.book)
        return Run(effects, Gas(receipt["gasUsed"]))

    def code_gas(self, message: Message, run: Run) -> Gas:
        """Returns the gas that the code spent on `run`, a call that sent `message`."""
        base = self._send(message.payload, message.sender,
                          {"to": NO_CODE, "data": self._encode(message.payload)})
        return Gas(run.gas_used - base["gasUsed"])

    def address(self, name: DeploymentName) -> ChecksumAddress:
        """Returns the address of the deployment `name`. Errors with RuntimeError when the build
        has no such deployment."""
        if name not in self.book:
            raise RuntimeError(f"the {self.build.label} build has no deployment {name}")
        return self.book[name]

    def _send(self, payload: Payload, sender: AccountIndex, tx: TxParams) -> TxReceipt:
        """Sends `tx` with the value of `payload` from the account `sender`, and returns the
        receipt, whether or not the transaction succeeds. Errors as Node.account does."""
        return self.node.receipt({**tx, "from": self.node.account(sender),
                                  "value": Wei(payload.value), "gas": TX_GAS})

    def _encode(self, payload: Payload) -> bytes:
        """Returns the bytes of `payload`, with the address of each account and deployment it
        names. Errors as Node.account and Session.address do."""
        def address(a: AddressArg) -> Word:
            if isinstance(a, Account):
                return _word(self.node.account(a.index))
            return _word(self.address(a.name))
        return payload.encode(address)

    def _effects(self, receipt: TxReceipt, output: bytes, book: Addresses) -> Effects:
        """Returns what the transaction of `receipt` did. Its storage effects cover only the
        deployments in `book`."""
        success = _succeeded(receipt)
        storage = self._storage_diff(receipt, book) if success else {}
        logs = tuple(Log(tuple(e["topics"]), e["data"]) for e in receipt["logs"])
        return Effects(success, output, logs, storage)

    def _storage_diff(self, receipt: TxReceipt,
                      book: Addresses) -> dict[DeploymentName, Storage]:
        """Returns the storage slots of each deployment of `book` that the transaction of
        `receipt` changed, leaving out the deployments with none."""
        diff = self.node.state_diff(receipt)
        changed = {name: _changed_slots(_storage(diff["pre"], a), _storage(diff["post"], a))
                   for name, a in book.items()}
        return {name: slots for name, slots in changed.items() if slots}
