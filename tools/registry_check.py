#!/usr/bin/env python3
"""Check the registries (registry/, docs/adr/0031-deployment-registry.md and
docs/adr/0034-compiler-registry.md) on a local anvil node.

It builds registry/ as Sourcify rebuilds it (docs/adr/0033-verify-on-sourcify.md), checks that
each contract's code fits EIP-170 and EIP-3860, and that registry/<contract>.abi.json is the
ABI that `fe build` writes. With --write-abi, it writes those files instead. Then it copies
CreateX's code from Arbitrum One to the node, deploys fe0-chain, CompilerRegistry with the
node's first account as its admin, and Registry, and checks that:

- only the admin adds or removes a compiler, a compiler is listed once, `add` emits the
  compiler's version, and the admin role moves in two steps;
- `deploy` errors with UnlistedCompiler for a compiler that the list lacks;
- `deploy` creates corpus/counter.fe at the address that CreateX gives for its init code and
  the salt, records it and adds it to the caller's set. Its `Registered` event and its state
  hold what ADR 0031 lists;
- a second `deploy` of the same program with the same salt creates nothing, and adds the
  contract to each caller's set once;
- the paged views give the right items from `start`, at most `limit`, and none past the end;
- `deploy` records a contract that CreateX created outside the registry;
- `deploy` errors with the Compiler's CompileError on a program with an error, and with
  CreateX's FailedContractCreation when the init code reverts;
- each contract's `version()` returns the version in registry/fe.toml.

It prints the gas of each deployment and transaction.
"""
import argparse
import sys
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple, NewType, Self

from eth_abi.abi import encode as abi_encode
from eth_typing import ChecksumAddress, Hash32
from eth_utils.crypto import keccak
from web3 import HTTPProvider, Web3
from web3.contract.contract import ContractFunction
from web3.exceptions import ContractLogicError
from web3.logs import DISCARD
from web3.types import TxReceipt

import fegen
import sourcify
from chain_check import (INIT_ARGS, INIT_ARGS_TYPES, OVERFLOWING_ARGS, Builds, Chain, Code,
                         CounterGet, Deployed, Initcode, abi_text, committed_file_check,
                         counter_args, counter_source, revert_data)
from deploy import ARBITRUM, CREATEX, CREATEX_ABI, Plan, create2_address, require_deployers
from embed import FailureMessage
from fegen import ROOT, AccountIndex, FeSource, Version, ingot_version
from node import Node

REGISTRY: Path = ROOT / "registry"
OUT: Path = ROOT / "out/registry"
WRITE_ABI: str = "--write-abi"
MANIFEST: Path = REGISTRY / "fe.toml"
# The most items that a check reads in one call of a paged view.
LIMIT: int = 10
ZERO: ChecksumAddress = Web3.to_checksum_address(bytes(20))
# The roles of the node's accounts in the checks: the first admin, another account that
# becomes the next admin, and an account with no role.
ADMIN: AccountIndex = AccountIndex(0)
OTHER: AccountIndex = AccountIndex(1)
STRANGER: AccountIndex = AccountIndex(2)
# A program with an error.
BAD_SOURCE: FeSource = FeSource("contract C { x: u256 }\n$")

# The salt that a caller passes to Registry's `deploy`.
Salt = NewType("Salt", bytes)


def createx_salt(salt: Salt) -> Hash32:
    """Returns the salt that Registry passes CreateX for `salt`
    (docs/adr/0031-deployment-registry.md, "Deploying")."""
    return Hash32(keccak(salt))


# The salts of the counter's deployments through the registry, of the one outside it, of the
# program with an error, and of the program whose init reverts.
COUNTER_SALT: Salt = Salt(b"\x01" * 32)
OUTSIDE_SALT: Salt = Salt(b"\x02" * 32)
BAD_SALT: Salt = Salt(b"\x03" * 32)
REVERTING_SALT: Salt = Salt(b"\x04" * 32)


class Name(StrEnum):
    """A contract of registry/."""

    COMPILERS = "CompilerRegistry"
    REGISTRY = "Registry"

    def interface(self) -> Path:
        """Returns the committed file that holds the contract's ABI for callers."""
        return REGISTRY / f"{self}.abi.json"

    def id(self) -> sourcify.ContractId:
        """Returns the contract's identifier in registry/'s source files."""
        path = {Name.COMPILERS: "src/compilers.fe", Name.REGISTRY: "src/registry.fe"}[self]
        return sourcify.ContractId(sourcify.SourcePath(path), self)


def version() -> Version:
    """Returns the version of registry/ that MANIFEST holds."""
    return ingot_version(MANIFEST)


def _address_arg(address: ChecksumAddress) -> bytes:
    return abi_encode(["address"], [address])


class RegistryBuilds(NamedTuple):
    """registry/ built as Sourcify rebuilds it, so the code matches what Sourcify verifies
    (docs/adr/0033-verify-on-sourcify.md)."""

    sources: sourcify.Sources
    compilers: Code[Name]
    registry: Code[Name]

    @classmethod
    def build(cls) -> Self:
        """Builds registry/. Exits as `fegen.fe_build` does."""
        sources = sourcify.Sources.read(REGISTRY)
        sources.build(OUT / "ingot", OUT)
        return cls(sources, Code.read(OUT, Name.COMPILERS), Code.read(OUT, Name.REGISTRY))

    def all(self) -> list[Code[Name]]:
        return [self.compilers, self.registry]

    def failures(self) -> list[FailureMessage]:
        """Returns a message for each EIP-170 or EIP-3860 limit that a contract's code exceeds,
        and one for each committed interface that differs from its contract's ABI."""
        return [m for b in self.all() for m in b.oversize() + committed_file_check(
            b.contract.interface(), abi_text(b.abi), f"tools/registry_check.py {WRITE_ABI}")]

    def compilers_initcode(self, admin: ChecksumAddress) -> Initcode:
        """Returns the init code of CompilerRegistry with `admin` as its admin
        (docs/adr/0034-compiler-registry.md)."""
        return Initcode(self.compilers.deploy_code + _address_arg(admin))

    def registry_initcode(self, compilers: ChecksumAddress) -> Initcode:
        """Returns the init code of Registry that takes the compilers that the
        CompilerRegistry at `compilers` lists (docs/adr/0034-compiler-registry.md)."""
        return Initcode(self.registry.deploy_code + _address_arg(compilers))

    def plan(self, admin: ChecksumAddress) -> Plan[Name]:
        """Returns the plan of both registries with `admin` as CompilerRegistry's admin."""
        compilers = self.compilers_initcode(admin)
        return Plan({Name.COMPILERS: compilers,
                     Name.REGISTRY: self.registry_initcode(create2_address(compilers))})


class Page(NamedTuple):
    """An AddressPage of registry/."""

    total: int
    items: list[ChecksumAddress]


def page(fn: ContractFunction) -> Page:
    """Returns the page that the paged view call `fn` returns by `eth_call`."""
    return Page(*fn.call())


class Deployment(NamedTuple):
    """Registry's Deployment (registry/src/registry.fe)."""

    addr: ChecksumAddress
    created: bool


class Record(NamedTuple):
    """Registry's Record (registry/src/registry.fe)."""

    registered_block: int
    compiler: ChecksumAddress
    src_hash: bytes


class AddressError(StrEnum):
    """An error with one address that a registry, or CreateX for it, reverts with."""

    UNLISTED = "UnlistedCompiler(address)"
    LISTED = "Listed(address)"
    NOT_LISTED = "NotListed(address)"
    NOT_ADMIN = "NotAdmin(address)"
    NOT_PENDING_ADMIN = "NotPendingAdmin(address)"
    FAILED_CREATION = "FailedContractCreation(address)"

    def data(self, address: ChecksumAddress) -> bytes:
        """Returns the revert data of the error with `address`."""
        return keccak(self.encode())[:4] + _address_arg(address)


class Deploy(NamedTuple):
    """A `deploy` through the registry, and its transaction."""

    deployment: Deployment
    receipt: TxReceipt


class Checker:
    def __init__(self, node: Node, chain: Chain, builds: RegistryBuilds) -> None:
        self.node = node
        self.compiler = chain.compiler
        w3 = node.w3
        compilers = Deployed.create(node, builds.compilers_initcode(node.account(ADMIN)))
        print(f"deploy CompilerRegistry: {compilers.gas:,} gas, at {compilers.address}")
        registry = Deployed.create(node, builds.registry_initcode(compilers.address))
        print(f"deploy Registry: {registry.gas:,} gas, at {registry.address}")
        self.compilers = builds.compilers.at(w3, compilers.address)
        self.registry = builds.registry.at(w3, registry.address)
        self.version = version()
        self.failures: list[FailureMessage] = []

    def expect(self, what: str, got: object, want: object) -> None:
        if got != want:
            self.failures.append(FailureMessage(f"{what}: got {got!r}, want {want!r}"))

    def send(self, fn: ContractFunction, index: AccountIndex, name: str) -> TxReceipt:
        receipt = self.node.transact(fn.build_transaction({"from": self.node.account(index)}))
        print(f"{name}: {receipt['gasUsed']:,} gas")
        return receipt

    def reverts(self, fn: ContractFunction, index: AccountIndex) -> bytes | None:
        """Returns the revert data of `fn` by `eth_call`, or None when it does not revert."""
        try:
            fn.call({"from": self.node.account(index)})
        except ContractLogicError as e:
            return revert_data(e)
        return None

    def counter_initcode(self) -> Initcode:
        code: bytes = self.compiler.functions.compile(counter_source().encode()).call()
        return Initcode(code + counter_args(self.node.w3))

    def deploy_call(self, salt: Salt, src: FeSource | None = None,
                    args: bytes | None = None) -> ContractFunction:
        w3 = self.node.w3
        return self.registry.functions.deploy(
            self.compiler.address, salt, (src or counter_source()).encode(),
            counter_args(w3) if args is None else args)

    def deploy(self, salt: Salt, index: AccountIndex, name: str) -> Deploy:
        fn = self.deploy_call(salt)
        deployment = Deployment(*fn.call({"from": self.node.account(index)}))
        return Deploy(deployment, self.send(fn, index, name))

    def info(self, addr: ChecksumAddress) -> Record:
        return Record(*self.registry.functions.info(addr).call())

    def check_compilers(self) -> None:
        """Checks the compiler list and that `deploy` refuses an unlisted compiler."""
        f = self.compilers.functions
        compiler = self.compiler.address
        self.expect("deploy with an unlisted compiler",
                    self.reverts(self.deploy_call(COUNTER_SALT), ADMIN),
                    AddressError.UNLISTED.data(compiler))
        self.expect("add by another account", self.reverts(f.add(compiler), OTHER),
                    AddressError.NOT_ADMIN.data(self.node.account(OTHER)))
        receipt = self.send(f.add(compiler), ADMIN, "add")
        [added] = self.compilers.events.CompilerAdded().process_receipt(receipt,
                                                                         errors=DISCARD)
        self.expect("CompilerAdded", dict(added["args"]),
                    {"compiler": compiler, "version": self.compiler.functions.version().call()})
        self.expect("add of a listed compiler", self.reverts(f.add(compiler), ADMIN),
                    AddressError.LISTED.data(compiler))
        self.expect("isListed", f.isListed(compiler).call(), True)
        self.expect("compilers", page(f.compilers(0, LIMIT)), Page(1, [compiler]))
        self.expect("version()", f.version().call(), self.version)

    def check_create(self) -> ChecksumAddress:
        """Checks the first `deploy` of the counter, and returns its address."""
        d = self.deploy(COUNTER_SALT, ADMIN, "deploy (creates)")
        addr = d.deployment.addr
        self.expect("deploy: created", d.deployment.created, True)
        want = create2_address(self.counter_initcode(), createx_salt(COUNTER_SALT))
        self.expect("deploy: address", addr, want)
        self.failures += CounterGet.call(self.node.w3, addr).failures()
        events = self.registry.events
        [r] = events.Registered().process_receipt(d.receipt, errors=DISCARD)
        src = counter_source().encode()
        self.expect("Registered", dict(r["args"]), {
            "addr": addr, "compiler": self.compiler.address, "src_hash": keccak(src),
            "salt": COUNTER_SALT, "src": src, "args": counter_args(self.node.w3)})
        f = self.registry.functions
        self.expect("info", self.info(addr),
                    Record(d.receipt["blockNumber"], self.compiler.address, keccak(src)))
        self.expect("contracts", page(f.contracts(0, LIMIT)), Page(1, [addr]))
        self.expect("contractsOf", page(f.contractsOf(self.node.account(ADMIN), 0, LIMIT)),
                    Page(1, [addr]))
        self.expect("version()", f.version().call(), self.version)
        return addr

    def check_again(self, addr: ChecksumAddress) -> None:
        """Checks a second and a third `deploy` of the counter with the same salt."""
        d = self.deploy(COUNTER_SALT, OTHER, "deploy (exists)")
        self.expect("second deploy: address", d.deployment.addr, addr)
        self.expect("second deploy: created", d.deployment.created, False)
        registered = self.registry.events.Registered().process_receipt(d.receipt,
                                                                        errors=DISCARD)
        self.expect("second deploy: Registered events", len(registered), 0)
        self.deploy(COUNTER_SALT, ADMIN, "deploy (exists, same caller)")
        f = self.registry.functions
        self.expect("contracts", page(f.contracts(0, LIMIT)).total, 1)
        self.expect("contractsOf the second caller",
                    page(f.contractsOf(self.node.account(OTHER), 0, LIMIT)), Page(1, [addr]))
        self.expect("contractsOf the first caller, twice",
                    page(f.contractsOf(self.node.account(ADMIN), 0, LIMIT)), Page(1, [addr]))

    def check_outside(self) -> None:
        """Checks `deploy` of a contract that CreateX created outside the registry."""
        createx = self.node.w3.eth.contract(CREATEX, abi=CREATEX_ABI)
        create = createx.functions.deployCreate2(createx_salt(OUTSIDE_SALT),
                                                 self.counter_initcode())
        self.send(create, ADMIN, "CreateX deployCreate2")
        d = self.deploy(OUTSIDE_SALT, OTHER, "deploy (outside)")
        addr = d.deployment.addr
        self.expect("deploy of a contract created outside: created", d.deployment.created,
                    False)
        self.expect("deploy of a contract created outside: recorded",
                    self.info(addr).compiler, self.compiler.address)
        f = self.registry.functions
        first = page(f.contracts(0, LIMIT)).items[0]
        self.expect("contracts from 1", page(f.contracts(1, LIMIT)), Page(2, [addr]))
        self.expect("contracts with limit 1", page(f.contracts(0, 1)), Page(2, [first]))
        self.expect("contracts past the end", page(f.contracts(5, LIMIT)), Page(2, []))

    def check_errors(self) -> None:
        """Checks `deploy` of a program with an error, and of one whose init reverts."""
        bad = self.deploy_call(BAD_SALT, BAD_SOURCE, b"")
        failure = fegen.Failure.decode(self.reverts(bad, ADMIN) or b"")
        self.expect("deploy of a program with an error is a CompileError",
                    isinstance(failure, fegen.CompileError), True)
        args = self.node.w3.codec.encode(INIT_ARGS_TYPES, OVERFLOWING_ARGS)
        init = self.deploy_call(REVERTING_SALT, FeSource(INIT_ARGS.read_text()), args)
        self.expect("deploy of a program whose init reverts", self.reverts(init, ADMIN),
                    AddressError.FAILED_CREATION.data(CREATEX))

    def check_admin(self) -> None:
        """Checks the two-step transfer of the admin role, and `remove`."""
        f = self.compilers.functions
        admin, other = self.node.account(ADMIN), self.node.account(OTHER)
        compiler = self.compiler.address
        self.expect("transferAdmin by another account",
                    self.reverts(f.transferAdmin(other), OTHER),
                    AddressError.NOT_ADMIN.data(other))
        self.send(f.transferAdmin(other), ADMIN, "transferAdmin")
        self.expect("pendingAdmin", f.pendingAdmin().call(), other)
        self.expect("acceptAdmin by another account", self.reverts(f.acceptAdmin(), STRANGER),
                    AddressError.NOT_PENDING_ADMIN.data(self.node.account(STRANGER)))
        receipt = self.send(f.acceptAdmin(), OTHER, "acceptAdmin")
        [changed] = self.compilers.events.AdminChanged().process_receipt(receipt,
                                                                          errors=DISCARD)
        self.expect("AdminChanged", dict(changed["args"]), {"previous": admin, "admin": other})
        self.expect("admin", (f.admin().call(), f.pendingAdmin().call()), (other, ZERO))
        self.expect("remove by the old admin", self.reverts(f.remove(compiler), ADMIN),
                    AddressError.NOT_ADMIN.data(admin))
        self.send(f.remove(compiler), OTHER, "remove")
        self.expect("compilers after remove", page(f.compilers(0, LIMIT)), Page(0, []))
        self.expect("remove of an unlisted compiler", self.reverts(f.remove(compiler), OTHER),
                    AddressError.NOT_LISTED.data(compiler))
        self.expect("deploy after remove",
                    self.reverts(self.deploy_call(COUNTER_SALT), ADMIN),
                    AddressError.UNLISTED.data(compiler))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(WRITE_ABI, action="store_true", help="write registry/<contract>.abi.json")
    write_abi: bool = ap.parse_args().write_abi
    builds = RegistryBuilds.build()
    for b in builds.all():
        print(b.size_line())
        if write_abi:
            b.contract.interface().write_text(abi_text(b.abi))
    failures = builds.failures()
    createx_code = require_deployers(Web3(HTTPProvider(ARBITRUM["rpc"])))[CREATEX]
    with Node() as node:
        node.set_code(CREATEX, createx_code)
        checker = Checker(node, Chain.deploy(node, Builds.build()), builds)
        checker.check_compilers()
        addr = checker.check_create()
        checker.check_again(addr)
        checker.check_outside()
        checker.check_errors()
        checker.check_admin()
        failures += checker.failures
    sys.exit("\n".join(failures) or None)


if __name__ == "__main__":
    main()
