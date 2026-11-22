#!/usr/bin/env python3
"""Deploy the compiler on chain (fe0-chain, DESIGN.md §8) to Arbitrum One, and run its demo.

It deploys only a release (fe0-chain/README.md, "Releases"), so it errors unless HEAD has the
release's tag and the working tree has no changes outside deployments/.
It builds fe0-chain at `-O s`, then deploys the four phase contracts and Compiler in one
transaction, so either all five are created or none is (DESIGN.md §8, "Deployment"). The
user approves each transaction in their browser wallet through browser-web3-signer, so no
private key is in the repo or the shell. Then the demo:

- calls `version()`, which must return the release's version;
- compiles corpus/counter.fe with `compile(bytes)` by `eth_call`, which costs nothing;
- deploys it with `deploy(bytes,bytes)` in a transaction, with start value 2;
- calls `Get` on the new contract.

The deployment transaction leaves out each contract that already has code at its address, so
a run after a full deployment only runs the demo. deployments/<chain id>.json records the
release and the addresses. Errors when the file holds another release or other addresses than
this build's, or lacks a field or a contract. Remove the file to deploy this build.

With --rehearse, it does all of this on a local anvil node, which signs for the wallet. It
copies the code of Multicall3 and CreateX, which the deployment transaction calls, to the node
from the chain at --rpc. A rehearsal also runs on a commit with no tag or with changes, and
records HEAD.
"""
import argparse
import json
import subprocess
import sys
from collections.abc import Iterable
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, NewType, Protocol, Self, TypedDict

from eth_typing import ABI, ChecksumAddress, Hash32, HexStr
from eth_utils.crypto import keccak
from hexbytes import HexBytes
from web3 import HTTPProvider, Web3
from web3.types import TxParams, TxReceipt

from chain_check import (COUNTER, Builds, Contract, CounterGet, Initcode, Version,
                         check_version, counter_args, counter_source, interface, version)
from fegen import ROOT
from node import Node

DEPLOYMENTS: Path = ROOT / "deployments"
SIGNER: str = "browser-web3-signer"

# A URL, such as a JSON-RPC endpoint.
Url = NewType("Url", str)


class Chain(TypedDict):
    """A chain that Compiler runs on."""

    id: int
    name: str
    rpc: Url
    # The block explorer, for the playground's links.
    explorer: Url


ARBITRUM: Chain = Chain(id=42161, name="Arbitrum One", rpc=Url("https://arb1.arbitrum.io/rpc"),
                        explorer=Url("https://arbiscan.io"))

# Multicall3 and CreateX, each at the same address on every chain that has it.
MULTICALL3: ChecksumAddress = Web3.to_checksum_address(
    "0xcA11bde05977b3631167028862bE2a173976CA11")
CREATEX: ChecksumAddress = Web3.to_checksum_address(
    "0xba5Ed099633D3B313e4D5F7bdc1305d3c28ba5Ed")
MULTICALL3_ABI: ABI = [{
    "type": "function", "name": "aggregate3", "stateMutability": "payable",
    "inputs": [{"name": "calls", "type": "tuple[]", "components": [
        {"name": "target", "type": "address"}, {"name": "allowFailure", "type": "bool"},
        {"name": "callData", "type": "bytes"}]}],
    "outputs": [{"name": "returnData", "type": "tuple[]", "components": [
        {"name": "success", "type": "bool"}, {"name": "returnData", "type": "bytes"}]}]}]
CREATEX_ABI: ABI = [{
    "type": "function", "name": "deployCreate2", "stateMutability": "payable",
    "inputs": [{"name": "salt", "type": "bytes32"}, {"name": "initCode", "type": "bytes"}],
    "outputs": [{"name": "newContract", "type": "address"}]}]
# CreateX's `_guard` mixes neither the sender nor the chain id into this salt, because its
# first 20 bytes are zero and its 21st byte is 0x00. So each contract's address depends only
# on its initcode (DESIGN.md §8, "Deployment").
SALT: Hash32 = Hash32(bytes(32))


def require_deployers(w3: Web3) -> dict[ChecksumAddress, HexBytes]:
    """Returns the code of MULTICALL3 and CREATEX on the chain of `w3`. Errors with RuntimeError
    when that chain has no code at one of them."""
    names = {MULTICALL3: "MULTICALL3", CREATEX: "CREATEX"}
    code = {address: w3.eth.get_code(address) for address in names}
    if missing := [f"{names[a]} ({a})" for a, c in code.items() if not c]:
        raise RuntimeError(f"chain {w3.eth.chain_id} has no code at {', '.join(missing)}")
    return code


def create2_address(initcode: Initcode) -> ChecksumAddress:
    """Returns the address at which CreateX's `deployCreate2` creates `initcode` with SALT."""
    guarded_salt = keccak(SALT)
    digest = keccak(b"\xff" + HexBytes(CREATEX) + guarded_salt + keccak(initcode))
    return Web3.to_checksum_address(digest[12:])


class Call3(NamedTuple):
    """A call that Multicall3's `aggregate3` makes."""

    target: ChecksumAddress
    allow_failure: bool
    call_data: HexStr


def deployment_data(initcodes: Iterable[Initcode]) -> HexBytes:
    """Returns the data of the call of MULTICALL3 that creates a contract from each of
    `initcodes` (DESIGN.md §8, "Deployment")."""
    w3 = Web3()
    createx = w3.eth.contract(CREATEX, abi=CREATEX_ABI)
    calls = [Call3(target=CREATEX, allow_failure=False,
                   call_data=createx.encode_abi("deployCreate2", [SALT, code]))
             for code in initcodes]
    multicall3 = w3.eth.contract(MULTICALL3, abi=MULTICALL3_ABI)
    return HexBytes(multicall3.encode_abi("aggregate3", [calls]))


class Plan(NamedTuple):
    """The contracts of a build as the deployment transaction creates them, with addresses known
    before it is sent (DESIGN.md §8, "Deployment")."""

    initcode: dict[Contract, Initcode]
    addresses: dict[Contract, ChecksumAddress]

    @classmethod
    def of(cls, builds: Builds) -> Self:
        """Returns the plan of `builds`. Compiler's constructor gets the phases' planned
        addresses."""
        initcode = builds.phase_initcode()
        addresses = {c: create2_address(code) for c, code in initcode.items()}
        initcode[Contract.COMPILER] = builds.compiler_initcode(addresses)
        addresses[Contract.COMPILER] = create2_address(initcode[Contract.COMPILER])
        return cls(initcode, addresses)


# A full git commit hash.
Commit = NewType("Commit", str)
# The git tag of a release (fe0-chain/README.md, "Releases").
Tag = NewType("Tag", str)


def git(*args: str) -> str:
    """Returns what git prints for `args`, stripped. Errors with RuntimeError when git fails."""
    r = subprocess.run(["git", "-C", str(ROOT), *args], stdout=subprocess.PIPE, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} exited with status {r.returncode}")
    return r.stdout.strip()


class Release(NamedTuple):
    """A release of fe0-chain (fe0-chain/README.md, "Releases")."""

    version: Version
    commit: Commit

    @classmethod
    def head(cls) -> Self:
        """Returns the version in fe0-chain/fe.toml with HEAD as its commit. Unlike `tagged`, it
        does not check that HEAD is a release."""
        return cls(version(), Commit(git("rev-parse", "HEAD")))

    @classmethod
    def tagged(cls) -> Self:
        """Returns the release at HEAD. Errors with RuntimeError when the working tree has
        changes outside DEPLOYMENTS, or when the release's tag is missing or names a commit
        other than HEAD."""
        release = cls.head()
        # The deployment file is committed after the release, so a rerun from the release's tag
        # finds it uncommitted.
        if git("status", "--porcelain", "--", ".", f":!{DEPLOYMENTS.relative_to(ROOT)}"):
            raise RuntimeError("the working tree has changes; commit them and tag the release")
        tag = release.tag
        if git("tag", "--list", tag) != tag:
            raise RuntimeError(f"no tag {tag}; tag HEAD with it to release it")
        if git("rev-parse", f"{tag}^{{commit}}") != release.commit:
            raise RuntimeError(f"the tag {tag} names a commit other than HEAD")
        return release

    @property
    def tag(self) -> Tag:
        return Tag(f"v{self.version}")

    def __str__(self) -> str:
        return f"{self.version} ({self.commit[:12]})"


class Sender(Protocol):
    """Sends transactions on one chain and waits for them."""

    w3: Web3

    def send(self, tx: TxParams) -> TxReceipt:
        """Sends `tx` and returns its receipt. Errors with RuntimeError when the transaction
        fails."""
        ...


class Wallet:
    """Sends each transaction from the user's browser wallet, through browser-web3-signer.
    Errors with RuntimeError when `rpc` serves a chain other than `chain_id`."""

    def __init__(self, rpc: Url, chain_id: int) -> None:
        self.w3 = Web3(HTTPProvider(rpc))
        self.chain_id = chain_id
        if (served := self.w3.eth.chain_id) != chain_id:
            raise RuntimeError(f"{rpc} serves chain {served}, not {chain_id}")

    def send(self, tx: TxParams) -> TxReceipt:
        """Sends `tx` from the wallet once the user approves it. Errors with RuntimeError when
        the user rejects it or the transaction fails."""
        args = [SIGNER, "--json", "evm", "send-transaction", "--chain", str(self.chain_id),
                "--data", HexBytes(tx.get("data", b"")).to_0x_hex()]
        if "to" in tx:
            args += ["--to", str(tx["to"])]
        r = subprocess.run(args, stdout=subprocess.PIPE, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"{SIGNER} exited with status {r.returncode}")
        sent = json.loads(r.stdout)
        print(f"  sent {sent['txHash']} {sent.get('explorer') or ''}", flush=True)
        receipt = self.w3.eth.wait_for_transaction_receipt(HexStr(sent["txHash"]), timeout=600)
        if not receipt["status"]:
            raise RuntimeError(f"the transaction {sent['txHash']} failed")
        return receipt


class Rehearsal:
    """Sends each transaction from the first account of a local anvil node."""

    def __init__(self, node: Node, origin: Web3) -> None:
        """Copies the code of MULTICALL3 and CREATEX from the chain of `origin` to `node`.
        Errors as `require_deployers` does, or as `Node.set_code` does."""
        self.w3 = node.w3
        self.node = node
        for address, code in require_deployers(origin).items():
            node.set_code(address, code)

    def send(self, tx: TxParams) -> TxReceipt:
        """Sends `tx` from the node's first account. Errors as `Node.transact` does."""
        return self.node.transact(tx)


class DeploymentFile(TypedDict):
    version: str
    commit: str
    contracts: dict[str, str]


class DeploymentRecord(NamedTuple):
    """A release of fe0-chain deployed on one chain, as its file records it. The file never
    records a partial deployment, because the five contracts are created in one transaction
    (DESIGN.md §8, "Deployment")."""

    release: Release
    addresses: dict[Contract, ChecksumAddress]

    @staticmethod
    def file(chain_id: int) -> Path:
        """Returns the file that records the deployment on the chain `chain_id`."""
        return DEPLOYMENTS / f"{chain_id}.json"

    @classmethod
    def on(cls, chain_id: int) -> Self:
        """Returns the record that the file of the chain `chain_id` holds. Errors as `read`
        does."""
        return cls.read(cls.file(chain_id))

    @classmethod
    def read(cls, path: Path) -> Self:
        """Returns the record that the file at `path` holds. Errors with OSError when there is
        no such file, or with RuntimeError when it lacks a field or a contract."""
        saved: DeploymentFile = json.loads(path.read_text())
        try:
            record = cls(Release(Version(saved["version"]), Commit(saved["commit"])),
                         {Contract(name): Web3.to_checksum_address(a)
                          for name, a in saved["contracts"].items()})
        except KeyError as e:
            raise RuntimeError(f"{path} lacks the field {e}") from e
        if lacking := [c for c in Contract if c not in record.addresses]:
            raise RuntimeError(f"{path} lacks the contracts {', '.join(lacking)}")
        return record

    def write(self, path: Path) -> None:
        """Writes the record to the file at `path`."""
        saved: DeploymentFile = {"version": self.release.version, "commit": self.release.commit,
                                 "contracts": {str(c): a for c, a in self.addresses.items()}}
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(saved, indent=2) + "\n")


@dataclass
class Deployment:
    path: Path
    release: Release
    plan: Plan

    @classmethod
    def open(cls, path: Path, release: Release, plan: Plan) -> Self:
        """Returns the deployment of `release` by `plan`, with its file at `path`. There may be
        no file yet. Errors with RuntimeError when the file holds another release or other
        addresses than the plan's, or lacks a field or a contract."""
        if path.exists():
            try:
                saved = DeploymentRecord.read(path)
            except RuntimeError as e:
                raise RuntimeError(f"{e}; remove it to deploy {release}") from e
            if saved.release != release:
                raise RuntimeError(f"{path.relative_to(ROOT)} holds release {saved.release};"
                                   f" remove it to deploy {release}")
            if saved.addresses != plan.addresses:
                raise RuntimeError(f"{path.relative_to(ROOT)} holds other addresses than this"
                                   " build's; remove it to deploy this build")
        return cls(path, release, plan)

    def without_code(self, w3: Web3, contracts: Iterable[Contract]) -> list[Contract]:
        """Returns those of `contracts` that have no code at their planned address on the chain
        of `w3`."""
        return [c for c in contracts if not w3.eth.get_code(self.plan.addresses[c])]

    def deploy_all(self, sender: Sender) -> ChecksumAddress:
        """Deploys each contract that has no code at its address yet, in one transaction that
        creates all of them or none (DESIGN.md §8, "Deployment"). Records every address in the
        deployment's file, and returns Compiler's address. Errors as `Sender.send` does, or with
        RuntimeError when the transaction leaves a contract without code, or as
        `require_deployers` does."""
        require_deployers(sender.w3)
        missing = self.without_code(sender.w3, self.plan.addresses)
        for c, address in self.plan.addresses.items():
            print(f"{c}: {'to deploy' if c in missing else 'deployed'} at {address}")
        if missing:
            data = deployment_data(self.plan.initcode[c] for c in missing)
            print(f"approve the deployment of {len(missing)} contracts in one transaction"
                  f" ({len(data):,} bytes of calldata)", flush=True)
            receipt = sender.send({"to": MULTICALL3, "data": data})
            print(f"deployed, {receipt['gasUsed']:,} gas", flush=True)
            if empty := self.without_code(sender.w3, missing):
                raise RuntimeError(f"the transaction left no code at {', '.join(empty)}")
        DeploymentRecord(self.release, self.plan.addresses).write(self.path)
        return self.plan.addresses[Contract.COMPILER]


def demo(sender: Sender, compiler: ChecksumAddress) -> None:
    """Deploys COUNTER with START through Compiler, and calls `Get`. Errors with RuntimeError
    when `version()` does not return the version in fe0-chain/fe.toml or `Get` does not return
    START, or as `Sender.send` does."""
    w3 = sender.w3
    contract = w3.eth.contract(compiler, abi=interface())
    got_version: str = contract.functions.version().call()
    print(f"version() by eth_call: {got_version!r}")
    if failures := check_version(got_version):
        raise RuntimeError("\n".join(failures))
    source = counter_source()
    code: bytes = contract.functions.compile(source.encode()).call()
    print(f"compile({COUNTER.name}) by eth_call: {len(code):,} bytes of deploy code")
    deploy = contract.functions.deploy(source.encode(), counter_args(w3))
    # The call runs on the same state as the transaction, as long as nobody else deploys through
    # Compiler in between, so it returns the address that the transaction creates.
    address: ChecksumAddress = deploy.call()
    print(f"deploy({COUNTER.name}): approve the transaction", flush=True)
    receipt = sender.send({"to": compiler, "data": HexBytes(deploy._encode_transaction_data())})
    got = CounterGet.call(w3, address)
    print(f"{COUNTER.name}: deployed at {address}, {receipt['gasUsed']:,} gas;"
          f" Get returns {got.value}")
    if failures := got.failures():
        raise RuntimeError("\n".join(failures))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rehearse", action="store_true", help="deploy on a local anvil node")
    ap.add_argument("--rpc", type=Url, default=ARBITRUM["rpc"], help="the chain's JSON-RPC URL")
    ap.add_argument("--chain", type=int, default=ARBITRUM["id"], help="the chain id")
    args = ap.parse_args()
    builds = Builds.build()
    if failures := builds.oversize():
        sys.exit("\n".join(failures))
    plan = Plan.of(builds)
    try:
        with ExitStack() as stack:
            sender: Sender
            if args.rehearse:
                sender = Rehearsal(stack.enter_context(Node()), Web3(HTTPProvider(args.rpc)))
                rehearsal = ROOT / "out/rehearsal.json"
                rehearsal.unlink(missing_ok=True)
                deployment = Deployment.open(rehearsal, Release.head(), plan)
            else:
                sender = Wallet(args.rpc, args.chain)
                deployment = Deployment.open(DeploymentRecord.file(args.chain),
                                             Release.tagged(), plan)
            demo(sender, deployment.deploy_all(sender))
    except RuntimeError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
