#!/usr/bin/env python3
"""Deploy the compiler on chain (fe0-chain, DESIGN.md §8) to Arbitrum One, and run its demo.

It builds fe0-chain as Sourcify rebuilds it (docs/adr/0033-verify-on-sourcify.md), then
deploys the four phase contracts and Compiler in one transaction, so either all five are
created or none is (docs/adr/0028-one-transaction-deploy.md). Then it submits their source to
Sourcify and waits for the matches. The user approves each transaction in their browser wallet
through browser-web3-signer, so no private key is in the repo or the shell. Then the demo:

- calls `version()`, which must return the version in fe0-chain/fe.toml;
- compiles corpus/counter.fe with `compile(bytes)` by `eth_call`, which costs nothing;
- deploys it with `deploy(bytes,bytes)` in a transaction, with start value 2;
- calls `Get` on the new contract.

The deployment transaction leaves out each contract that already has code at its address, so a
run after a full deployment only runs the demo. deployments/<chain id>.json records the version,
the addresses and Sourcify's matches. Errors when the file holds another version or other
addresses than this build's, or is not such a record. Remove the file to deploy this build.

With --rehearse, it does all of this on a local anvil node, which signs for the wallet. A
rehearsal skips Sourcify. It copies the code of Multicall3 and CreateX, which the deployment
transaction calls, to the node from the chain at --rpc.
"""
import abc
import argparse
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, ClassVar, NamedTuple, Self, TypedDict

from eth_typing import ABI, ChecksumAddress, Hash32, HexStr
from eth_utils.crypto import keccak
from hexbytes import HexBytes
from pydantic import (AfterValidator, BaseModel, ConfigDict, Field, ValidationError,
                      model_validator)
from web3 import HTTPProvider, Web3
from web3.contract.contract import Contract as Web3Contract, ContractFunction
from web3.types import TxParams, TxReceipt

from chain_check import COUNTER, Builds, Contract, Initcode, check_version, version
from fegen import ROOT, ChainId, Url, Version
from node import Node
from sourcify import Identified, Match, Sources

DEPLOYMENTS: Path = ROOT / "deployments"
SIGNER: str = "browser-web3-signer"

# A ChecksumAddress in a JSON record, which holds it in any case.
Address = Annotated[ChecksumAddress, AfterValidator(Web3.to_checksum_address)]


class Currency(TypedDict):
    """The native currency of a chain, which pays its gas."""

    name: str
    symbol: str
    decimals: int


class Chain(TypedDict):
    """A chain that Compiler runs on. playground.py writes a Chain into the playground's
    config.ts as it is, so l1Blocks and logRange are in camelCase, as the TypeScript type
    `Chain` spells them."""

    id: ChainId
    name: str
    rpc: Url
    # The block explorer, for the playground's links.
    explorer: Url
    currency: Currency
    # Whether `block.number` gives Ethereum's block number, not this chain's
    # (docs/adr/0031-deployment-registry.md, "Reading").
    l1Blocks: bool
    # The most blocks that one `eth_getLogs` of several addresses may span at `rpc`.
    logRange: int


ARBITRUM: Chain = Chain(id=ChainId(42161), name="Arbitrum One",
                        rpc=Url("https://arb1.arbitrum.io/rpc"),
                        explorer=Url("https://arbiscan.io"),
                        currency=Currency(name="Ether", symbol="ETH", decimals=18),
                        l1Blocks=True, logRange=100_000)

# Multicall3 and CreateX, each at the same address on every chain that has it. Their sources and
# their lists of chains: https://github.com/mds1/multicall3#deployments-and-abi and
# https://github.com/pcaversaccio/createx#createx-deployments
MULTICALL3: ChecksumAddress = Web3.to_checksum_address(
    "0xcA11bde05977b3631167028862bE2a173976CA11")
MULTICALL3_ABI: ABI = [{
    "type": "function", "name": "aggregate3", "stateMutability": "payable",
    "inputs": [{"name": "calls", "type": "tuple[]", "components": [
        {"name": "target", "type": "address"}, {"name": "allowFailure", "type": "bool"},
        {"name": "callData", "type": "bytes"}]}],
    "outputs": [{"name": "returnData", "type": "tuple[]", "components": [
        {"name": "success", "type": "bool"}, {"name": "returnData", "type": "bytes"}]}]}]
# CreateX's `_guard` mixes neither the sender nor the chain id into this salt, because its
# first 20 bytes are zero and its 21st byte is 0x00. So each contract's address depends only
# on its initcode (docs/adr/0028-one-transaction-deploy.md).
SALT: Hash32 = Hash32(bytes(32))


class CreateX(NamedTuple):
    """CreateX at `address`, which creates contracts with `CREATE2`."""

    address: ChecksumAddress

    def at(self, w3: Web3) -> Web3Contract:
        """Returns CreateX on the chain of `w3`, with only `deployCreate2` in its ABI."""
        return w3.eth.contract(self.address, abi=[{
            "type": "function", "name": "deployCreate2", "stateMutability": "payable",
            "inputs": [{"name": "salt", "type": "bytes32"},
                       {"name": "initCode", "type": "bytes"}],
            "outputs": [{"name": "newContract", "type": "address"}]}])

    def deploy_call(self, w3: Web3, initcode: Initcode,
                    salt: Hash32 = SALT) -> ContractFunction:
        """Returns the call of `deployCreate2` that creates `initcode` with `salt`."""
        return self.at(w3).functions.deployCreate2(salt, initcode)

    def address_of(self, initcode: Initcode, salt: Hash32 = SALT) -> ChecksumAddress:
        """Returns the address at which `deployCreate2` creates `initcode` with `salt`. It holds
        only for a salt that CreateX hashes once and mixes nothing into, such as SALT
        (docs/adr/0028-one-transaction-deploy.md) or a hashed registry salt
        (docs/adr/0031-deployment-registry.md, "Deploying")."""
        guarded_salt = keccak(salt)
        digest = keccak(b"\xff" + HexBytes(self.address) + guarded_salt + keccak(initcode))
        return Web3.to_checksum_address(digest[12:])


CREATEX: CreateX = CreateX(Web3.to_checksum_address(
    "0xba5Ed099633D3B313e4D5F7bdc1305d3c28ba5Ed"))


def require_deployers(w3: Web3) -> dict[ChecksumAddress, HexBytes]:
    """Returns the code of MULTICALL3 and CREATEX on the chain of `w3`. Errors with RuntimeError
    when that chain has no code at one of them."""
    names = {MULTICALL3: "MULTICALL3", CREATEX.address: "CREATEX"}
    code = {address: w3.eth.get_code(address) for address in names}
    if missing := [f"{names[a]} ({a})" for a, c in code.items() if not c]:
        raise RuntimeError(f"chain {w3.eth.chain_id} has no code at {', '.join(missing)}")
    return code


class Call3(NamedTuple):
    """A call that Multicall3's `aggregate3` makes."""

    target: ChecksumAddress
    allow_failure: bool
    call_data: HexStr


def deployment_data(initcodes: Iterable[Initcode]) -> HexBytes:
    """Returns the data of the call of MULTICALL3 that creates a contract from each of
    `initcodes` (docs/adr/0028-one-transaction-deploy.md)."""
    w3 = Web3()
    calls = [Call3(target=CREATEX.address, allow_failure=False,
                   call_data=CREATEX.deploy_call(w3, code)._encode_transaction_data())
             for code in initcodes]
    multicall3 = w3.eth.contract(MULTICALL3, abi=MULTICALL3_ABI)
    return HexBytes(multicall3.encode_abi("aggregate3", [calls]))


class Sender(abc.ABC):
    """Sends transactions on one chain, and verifies and records what they deploy."""

    w3: Web3

    @abc.abstractmethod
    def account(self) -> ChecksumAddress:
        """Returns the account that sends the transactions."""

    @abc.abstractmethod
    def send(self, tx: TxParams) -> TxReceipt:
        """Sends `tx` and returns its receipt. Errors with RuntimeError when the transaction
        fails."""

    @abc.abstractmethod
    def verify[K: Identified](self, sources: Sources,
                              addresses: dict[K, ChecksumAddress]) -> dict[K, Match] | None:
        """Submits each contract at `addresses`, built from `sources`, to Sourcify and returns
        the matches, or returns None when Sourcify cannot see the chain. Errors as
        `Sources.verify` does."""

    @abc.abstractmethod
    def clear_rehearsal_record(self, record: type[DeployedRecord[Any]]) -> Path:
        """Removes the rehearsal's file of `record` when the sender is a rehearsal, so that each
        rehearsal deploys anew. Returns the file that records the sender's deployment: the
        file of its chain, or the rehearsal's file."""

    def send_call(self, fn: ContractFunction, what: str) -> TxReceipt:
        """Sends the call `fn`, once the user approves it, and returns the receipt. Errors as
        `send` does."""
        print(f"{what}: approve the transaction", flush=True)
        receipt = self.send({"to": fn.address, "data": HexBytes(fn._encode_transaction_data())})
        print(f"{what}: {receipt['gasUsed']:,} gas", flush=True)
        return receipt

    def deploy_chain(self, builds: Builds) -> DeploymentRecord:
        """Deploys fe0-chain's `builds`, leaving out each contract already on the chain, and
        returns its record. Errors with RuntimeError when a contract's code exceeds EIP-170 or
        EIP-3860, or as `Deployment.open` and `Deployment.deploy_all` do."""
        if failures := builds.oversize():
            raise RuntimeError("\n".join(failures))
        path = self.clear_rehearsal_record(DeploymentRecord)
        deployment = Deployment.open(path, version(), Plan.of(builds), DeploymentRecord)
        return deployment.deploy_all(
            self, builds.sources,
            lambda contracts, matches: DeploymentRecord(version=deployment.version,
                                                        contracts=contracts, sourcify=matches))

    def demo_compiler(self, compiler: ChecksumAddress, interface: ABI) -> None:
        """Deploys COUNTER through the Compiler at `compiler`, and calls `Get`. Errors with
        RuntimeError when `version()` does not return the version in fe0-chain/fe.toml or `Get`
        does not return COUNTER's start value, or as `send` does."""
        contract = self.w3.eth.contract(compiler, abi=interface)
        got_version: str = contract.functions.version().call()
        print(f"version() by eth_call: {got_version!r}")
        if failures := check_version(got_version):
            raise RuntimeError("\n".join(failures))
        name = COUNTER.path.name
        source = COUNTER.source()
        code: bytes = contract.functions.compile(source.encode()).call()
        print(f"compile({name}) by eth_call: {len(code):,} bytes of deploy code")
        deploy = contract.functions.deploy(source.encode(), COUNTER.args())
        # The call runs on the same state as the transaction, as long as nobody else deploys
        # through Compiler in between, so it returns the address that the transaction creates.
        address: ChecksumAddress = deploy.call()
        self.send_call(deploy, f"deploy({name})")
        got = COUNTER.get(self.w3, address)
        print(f"{name}: deployed at {address}; Get returns {got.value}")
        if failures := got.failures():
            raise RuntimeError("\n".join(failures))


class Plan[K: Identified](NamedTuple):
    """The contracts that one deployment transaction creates, by key, with addresses known
    before it is sent (docs/adr/0028-one-transaction-deploy.md)."""

    initcode: dict[K, Initcode]

    @classmethod
    def of(cls, builds: Builds) -> Plan[Contract]:
        """Returns the plan of fe0-chain's `builds`. Compiler's constructor gets the phases'
        planned addresses."""
        initcode = builds.phase_initcode()
        phases = {c: CREATEX.address_of(code) for c, code in initcode.items()}
        initcode[Contract.COMPILER] = builds.compiler_initcode(phases)
        return Plan(initcode)

    @property
    def addresses(self) -> dict[K, ChecksumAddress]:
        return {k: CREATEX.address_of(code) for k, code in self.initcode.items()}

    def check_record(self, path: Path, recorded: Mapping[K, ChecksumAddress]) -> None:
        """Errors with RuntimeError when `recorded`, which the file at `path` holds, are other
        addresses than the plan's."""
        if recorded != self.addresses:
            raise RuntimeError(f"{path.relative_to(ROOT)} holds other addresses than this"
                               " build's; remove it to deploy this build")

    def deploy(self, sender: Sender) -> None:
        """Creates each contract that has no code at its address yet, in one transaction that
        creates all of them or none. Errors as `Sender.send` and `require_deployers` do, or
        with RuntimeError when the transaction leaves a contract without code."""
        w3 = sender.w3
        require_deployers(w3)
        addresses = self.addresses

        def without_code(keys: Iterable[K]) -> list[K]:
            return [k for k in keys if not w3.eth.get_code(addresses[k])]
        missing = without_code(addresses)
        for k, address in addresses.items():
            print(f"{k}: {'to deploy' if k in missing else 'deployed'} at {address}")
        if not missing:
            return
        data = deployment_data(self.initcode[k] for k in missing)
        print(f"approve the deployment of {len(missing)} contracts in one transaction"
              f" ({len(data):,} bytes of calldata)", flush=True)
        receipt = sender.send({"to": MULTICALL3, "data": data})
        print(f"deployed, {receipt['gasUsed']:,} gas", flush=True)
        if empty := without_code(missing):
            raise RuntimeError(f"the transaction left no code for {', '.join(map(str, empty))}")


class _Connected(BaseModel):
    address: Address


class _Sent(BaseModel):
    tx_hash: HexStr = Field(alias="txHash")
    explorer: str | None = None


class Wallet(Sender):
    """Sends each transaction from the user's browser wallet, through browser-web3-signer.
    Errors with RuntimeError when `rpc` serves a chain other than `chain_id`."""

    def __init__(self, rpc: Url, chain_id: ChainId) -> None:
        self.w3 = Web3(HTTPProvider(rpc))
        self.chain_id = chain_id
        if (served := self.w3.eth.chain_id) != chain_id:
            raise RuntimeError(f"{rpc} serves chain {served}, not {chain_id}")
        self._account: ChecksumAddress | None = None

    def _signer[R: BaseModel](self, reply: type[R], command: str, *args: str) -> R:
        """Runs the signer's `command` with `args` on the wallet's chain, and returns its
        reply. Errors with RuntimeError when the signer fails or its reply is not a
        `reply`."""
        r = subprocess.run([SIGNER, "--json", "evm", command, "--chain", str(self.chain_id),
                            *args], stdout=subprocess.PIPE, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"{SIGNER} exited with status {r.returncode}")
        try:
            return reply.model_validate_json(r.stdout)
        except ValidationError as e:
            raise RuntimeError(f"{SIGNER} {command} replied {r.stdout!r}: {e}") from e

    def account(self) -> ChecksumAddress:
        """Returns the wallet's account, which the user connects in the browser on the first
        call. Errors with RuntimeError when the user does not connect it."""
        if self._account is None:
            self._account = self._signer(_Connected, "connect").address
        return self._account

    def send(self, tx: TxParams) -> TxReceipt:
        """Sends `tx` from the wallet once the user approves it. Errors with RuntimeError when
        the user rejects it or the transaction fails."""
        # A deployment's calldata is longer than Linux allows in one argument, so it goes
        # through a file.
        with tempfile.NamedTemporaryFile("w", suffix=".hex") as data:
            data.write(HexBytes(tx.get("data", b"")).to_0x_hex())
            data.flush()
            args = ["--data-file", data.name]
            if "to" in tx:
                args += ["--to", str(tx["to"])]
            sent = self._signer(_Sent, "send-transaction", *args)
        print(f"  sent {sent.tx_hash} {sent.explorer or ''}", flush=True)
        receipt = self.w3.eth.wait_for_transaction_receipt(sent.tx_hash, timeout=600)
        if not receipt["status"]:
            raise RuntimeError(f"the transaction {sent.tx_hash} failed")
        return receipt

    def verify[K: Identified](self, sources: Sources,
                              addresses: dict[K, ChecksumAddress]) -> dict[K, Match]:
        """Submits `sources` to Sourcify for each contract at `addresses`, and returns the
        matches. Errors as `Sources.verify` does."""
        matches = {}
        for k, address in addresses.items():
            matches[k] = sources.verify(self.chain_id, address, k.id())
            print(f"Sourcify, {k}: {matches[k]}", flush=True)
        return matches

    def clear_rehearsal_record(self, record: type[DeployedRecord[Any]]) -> Path:
        return record.file(self.chain_id)


class Rehearsal(Sender):
    """Sends each transaction from the first account of a local anvil node."""

    def __init__(self, node: Node, origin: Web3) -> None:
        """Copies the code of MULTICALL3 and CREATEX from the chain of `origin` to `node`.
        Errors as `require_deployers` does, or as `Node.set_code` does."""
        self.w3 = node.w3
        self.node = node
        for address, code in require_deployers(origin).items():
            node.set_code(address, code)

    @classmethod
    def start(cls, stack: ExitStack, rpc: Url) -> Self:
        """Starts a node that `stack` stops, and copies the deployers from the chain at `rpc` to
        it. Errors as `Node` and `__init__` do."""
        return cls(stack.enter_context(Node()), Web3(HTTPProvider(rpc)))

    def account(self) -> ChecksumAddress:
        return self.node.accounts[0]

    def send(self, tx: TxParams) -> TxReceipt:
        """Sends `tx` from the node's first account. Errors as `Node.transact` does."""
        return self.node.transact(tx)

    def verify[K: Identified](self, sources: Sources,
                              addresses: dict[K, ChecksumAddress]) -> None:
        """Returns None, since Sourcify cannot see the node."""
        return None

    def clear_rehearsal_record(self, record: type[DeployedRecord[Any]]) -> Path:
        """Removes the rehearsal's file of `record` and returns it."""
        record.REHEARSAL.unlink(missing_ok=True)
        return record.REHEARSAL


class JsonRecord(BaseModel):
    """A record that a deploy tool keeps in a JSON file."""

    model_config = ConfigDict(frozen=True)

    @classmethod
    def read(cls, path: Path) -> Self:
        """Returns the record that the file at `path` holds. Errors with OSError when there is
        no such file, or with RuntimeError when it holds no such record."""
        try:
            return cls.model_validate_json(path.read_text())
        except ValidationError as e:
            raise RuntimeError(f"{path} holds no {cls.__name__}: {e}") from e

    def write(self, path: Path) -> None:
        """Writes the record to the file at `path`."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2) + "\n")


class DeployedRecord[K: StrEnum](JsonRecord):
    """A version of a set of contracts deployed on one chain, with Sourcify's match for each
    (docs/adr/0033-verify-on-sourcify.md). A rehearsal's record has no matches."""

    # The directory of the records, one file for each chain, and the record of a rehearsal.
    DIR: ClassVar[Path]
    REHEARSAL: ClassVar[Path]

    version: Version
    contracts: dict[K, Address]
    sourcify: dict[K, Match] | None

    @classmethod
    def file(cls, chain_id: ChainId) -> Path:
        """Returns the file that records the deployment on the chain `chain_id`."""
        return cls.DIR / f"{chain_id}.json"

    @classmethod
    def on(cls, chain_id: ChainId) -> Self:
        """Returns the record that the file of the chain `chain_id` holds. Errors as `read`
        does."""
        return cls.read(cls.file(chain_id))

    @model_validator(mode="after")
    def _match_for_each_contract(self) -> Self:
        if self.sourcify is not None and self.sourcify.keys() != self.contracts.keys():
            raise ValueError("does not hold one Sourcify match for each contract")
        return self


class DeploymentRecord(DeployedRecord[Contract]):
    """fe0-chain's record. The file never records a partial deployment, because the five
    contracts are created in one transaction (docs/adr/0028-one-transaction-deploy.md)."""

    DIR: ClassVar[Path] = DEPLOYMENTS
    REHEARSAL: ClassVar[Path] = ROOT / "out/rehearsal.json"

    @model_validator(mode="after")
    def _every_contract(self) -> Self:
        if lacking := [c for c in Contract if c not in self.contracts]:
            raise ValueError(f"lacks the contracts {', '.join(lacking)}")
        return self

    @property
    def compiler(self) -> ChecksumAddress:
        return self.contracts[Contract.COMPILER]

    @classmethod
    def chain_ids(cls) -> list[ChainId]:
        """Returns the id of each chain that has a file, in ascending order. Errors with
        RuntimeError when a file's name is not a chain id."""
        ids = []
        for path in cls.DIR.glob("*.json"):
            if not path.stem.isdecimal():
                raise RuntimeError(f"{path} is named for no chain id")
            ids.append(ChainId(int(path.stem)))
        return sorted(ids)


@dataclass
class Deployment[K: Identified, R: DeployedRecord[Any]]:
    """A version of a set of contracts to deploy by `plan`, and the file at `path` that records
    it as an `R`."""

    path: Path
    version: Version
    plan: Plan[K]
    record: type[R]

    @classmethod
    def open(cls, path: Path, version: Version, plan: Plan[K], record: type[R]) -> Self:
        """Returns the deployment, whose file may not exist yet. Errors with RuntimeError when
        the file holds another version, other addresses than the plan's, or no `record`."""
        if path.exists():
            try:
                saved = record.read(path)
            except RuntimeError as e:
                raise RuntimeError(f"{e}; remove it to deploy {version}") from e
            if saved.version != version:
                raise RuntimeError(f"{path.relative_to(ROOT)} holds version {saved.version};"
                                   f" remove it to deploy {version}")
            plan.check_record(path, saved.contracts)
        return cls(path, version, plan, record)

    def deploy_all(self, sender: Sender, sources: Sources,
                   make: Callable[[dict[K, ChecksumAddress], dict[K, Match] | None], R]) -> R:
        """Deploys the plan, and writes the record that `make` makes of every address and its
        Sourcify match to the deployment's file. Returns the record. Errors as `Plan.deploy`
        and `Sender.verify` do."""
        self.plan.deploy(sender)
        addresses = self.plan.addresses
        saved = make(addresses, sender.verify(sources, addresses))
        saved.write(self.path)
        return saved


def chain_id_arg(text: str) -> ChainId:
    """Returns the chain id that the command-line argument `text` gives. Errors with
    ValueError when `text` is not a number."""
    return ChainId(int(text))


def chain_parser(doc: str | None) -> argparse.ArgumentParser:
    """Returns the parser of a tool's arguments that name a chain, with `doc` as its help."""
    ap = argparse.ArgumentParser(description=doc,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rpc", type=Url, default=ARBITRUM["rpc"], help="the chain's JSON-RPC URL")
    ap.add_argument("--chain", type=chain_id_arg, default=ARBITRUM["id"], help="the chain id")
    return ap


def deploy_parser(doc: str | None) -> argparse.ArgumentParser:
    """Returns the parser of a deploy tool's arguments, with `doc` as its help."""
    ap = chain_parser(doc)
    ap.add_argument("--rehearse", action="store_true", help="deploy on a local anvil node")
    return ap


def main() -> None:
    args = deploy_parser(__doc__).parse_args()
    builds = Builds.build()
    try:
        with ExitStack() as stack:
            sender: Sender = (Rehearsal.start(stack, args.rpc) if args.rehearse
                              else Wallet(args.rpc, args.chain))
            sender.demo_compiler(sender.deploy_chain(builds).compiler, builds.interface())
    except RuntimeError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
