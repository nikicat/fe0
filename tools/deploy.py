#!/usr/bin/env python3
"""Deploy the compiler on chain (fe0-chain, DESIGN.md §8) to Arbitrum One, and run its demo.

It deploys only a release (fe0-chain/README.md, "Releases"), so it errors unless HEAD has the
release's tag and the working tree has no changes outside deployments/.
It builds fe0-chain at `-O s`, then deploys the four phase contracts and Compiler. The user
approves each transaction in their browser wallet through browser-web3-signer, so no private key
is in the repo or the shell. Then the demo:

- calls `version()`, which must return the release's version;
- compiles corpus/counter.fe with `compile(bytes)` by `eth_call`, which costs nothing;
- deploys it with `deploy(bytes,bytes)` in a transaction, with start value 2;
- calls `Get` on the new contract.

deployments/<chain id>.json records the release, and each address as soon as its contract is
deployed. A run that stops part way resumes where it stopped, and a run after a full deployment
only runs the demo. Errors when the file holds another release or none; remove the file to
deploy this one.

With --rehearse, it does all of this on a local anvil node, which signs for the wallet. A
rehearsal also runs on a commit with no tag or with changes, and records HEAD.
"""
import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, NewType, Protocol, Self, TypedDict

from eth_typing import ChecksumAddress, HexStr
from hexbytes import HexBytes
from web3 import HTTPProvider, Web3
from web3.types import TxParams, TxReceipt

from chain_check import (COUNTER, Build, Builds, Contract, CounterGet, Version, check_version,
                         counter_args, counter_source, interface, version)
from fegen import ROOT
from node import Node

ARBITRUM_ONE: int = 42161
ARBITRUM_RPC: str = "https://arb1.arbitrum.io/rpc"
DEPLOYMENTS: Path = ROOT / "deployments"
SIGNER: str = "browser-web3-signer"


# A full git commit hash.
Commit = NewType("Commit", str)


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
        changes outside DEPLOYMENTS, or when the tag `v<version>` is missing or names a commit
        other than HEAD."""
        release = cls.head()
        # A run that stopped part way leaves its deployment file behind.
        if git("status", "--porcelain", "--", ".", f":!{DEPLOYMENTS.relative_to(ROOT)}"):
            raise RuntimeError("the working tree has changes; commit them and tag the release")
        tag = f"v{release.version}"
        if git("tag", "--list", tag) != tag:
            raise RuntimeError(f"no tag {tag}; tag HEAD with it to release it")
        if git("rev-parse", f"{tag}^{{commit}}") != release.commit:
            raise RuntimeError(f"the tag {tag} names a commit other than HEAD")
        return release

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
    """Sends each transaction from the user's browser wallet, through browser-web3-signer."""

    def __init__(self, rpc: str, chain_id: int) -> None:
        self.w3 = Web3(HTTPProvider(rpc))
        self.chain_id = chain_id

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

    def __init__(self, node: Node) -> None:
        self.w3 = node.w3
        self.node = node

    def send(self, tx: TxParams) -> TxReceipt:
        """Sends `tx` from the node's first account. Errors as `Node.transact` does."""
        return self.node.transact(tx)


class DeploymentFile(TypedDict):
    version: str
    commit: str
    contracts: dict[str, str]


@dataclass
class Deployment:
    """A release of fe0-chain deployed on one chain. Its file is written after each contract
    is deployed, so that a run that stops part way resumes where it stopped."""

    path: Path
    release: Release
    addresses: dict[Contract, ChecksumAddress]

    @staticmethod
    def file(chain_id: int) -> Path:
        """Returns the file that records the deployment on the chain `chain_id`."""
        return DEPLOYMENTS / f"{chain_id}.json"

    @classmethod
    def read(cls, path: Path) -> Self:
        """Returns the deployment that the file at `path` holds. Errors with OSError when there
        is no such file, or with RuntimeError when it lacks a field."""
        saved: DeploymentFile = json.loads(path.read_text())
        try:
            return cls(path, Release(Version(saved["version"]), Commit(saved["commit"])),
                       {Contract(name): Web3.to_checksum_address(a)
                        for name, a in saved["contracts"].items()})
        except KeyError as e:
            raise RuntimeError(f"{path} lacks the field {e}") from e

    def save(self) -> None:
        """Writes the deployment to its file."""
        saved: DeploymentFile = {"version": self.release.version, "commit": self.release.commit,
                                 "contracts": {str(c): a for c, a in self.addresses.items()}}
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(saved, indent=2) + "\n")

    @classmethod
    def resume(cls, path: Path, release: Release) -> Self:
        """Returns the deployment of `release` that the file at `path` holds, or one with no
        addresses when there is no file. Errors with RuntimeError when the file holds another
        release, or as `read` does."""
        if not path.exists():
            return cls(path, release, {})
        try:
            saved = cls.read(path)
        except RuntimeError as e:
            raise RuntimeError(f"{e}; remove it to deploy {release}") from e
        if saved.release != release:
            raise RuntimeError(f"{path.relative_to(ROOT)} holds release {saved.release};"
                               f" remove it to deploy {release}")
        return saved

    def deploy(self, sender: Sender, build: Build, initcode: bytes) -> ChecksumAddress:
        """Returns the address of `build`'s contract, and deploys `initcode` for it first when
        the file has none. Errors as `Sender.send` does, or with RuntimeError when the
        transaction creates no contract."""
        if build.contract in self.addresses:
            print(f"{build.contract}: deployed at {self.addresses[build.contract]}")
            return self.addresses[build.contract]
        print(f"{build.contract}: approve its deployment ({len(build.runtime):,} runtime bytes)",
              flush=True)
        receipt = sender.send({"data": HexBytes(initcode)})
        address = receipt["contractAddress"]
        if address is None:
            raise RuntimeError(f"the deployment of {build.contract} created no contract")
        print(f"{build.contract}: deployed at {address}, {receipt['gasUsed']:,} gas", flush=True)
        self.addresses[build.contract] = address
        self.save()
        return address

    def deploy_all(self, sender: Sender, builds: Builds) -> ChecksumAddress:
        """Deploys each contract that is not deployed yet, the phases first, and returns
        Compiler's address. Errors as `deploy` does."""
        phases = {b.contract.constructor_arg(): self.deploy(sender, b, b.initcode)
                  for b in builds.phases}
        factory = sender.w3.eth.contract(abi=interface(), bytecode=builds.compiler.initcode)
        initcode = HexBytes(factory.constructor(**phases).data_in_transaction)
        return self.deploy(sender, builds.compiler, initcode)


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
    ap.add_argument("--rpc", default=ARBITRUM_RPC, help="the chain's JSON-RPC URL")
    ap.add_argument("--chain", type=int, default=ARBITRUM_ONE, help="the chain id")
    args = ap.parse_args()
    builds = Builds.build()
    if failures := builds.oversize():
        sys.exit("\n".join(failures))
    try:
        if args.rehearse:
            with Node() as node:
                sender: Sender = Rehearsal(node)
                rehearsal = ROOT / "out/rehearsal.json"
                rehearsal.unlink(missing_ok=True)
                deployment = Deployment.resume(rehearsal, Release.head())
                demo(sender, deployment.deploy_all(sender, builds))
        else:
            sender = Wallet(args.rpc, args.chain)
            if sender.w3.eth.chain_id != args.chain:
                sys.exit(f"{args.rpc} serves chain {sender.w3.eth.chain_id}, not {args.chain}")
            deployment = Deployment.resume(Deployment.file(args.chain), Release.tagged())
            demo(sender, deployment.deploy_all(sender, builds))
    except RuntimeError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
