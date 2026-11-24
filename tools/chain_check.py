#!/usr/bin/env python3
"""Check the compiler on chain (fe0-chain, DESIGN.md §8) on a local anvil node.

It builds fe0-chain as Sourcify rebuilds it (`chain_sources`) and checks that each contract's
runtime code fits EIP-170 and its deploy code fits EIP-3860. Then it deploys the phase contracts
and Compiler on anvil, and:

- compiles every program of corpus/ with `compile(bytes)` by `eth_call`. The deploy code must
  be the CLI's, byte for byte;
- compiles every reject program of corpus/reject/. Compiler must revert with the CompileError
  of the program's `// expect:` header;
- deploys corpus/counter.fe with `deploy(bytes,bytes)` in a transaction, and calls it;
- calls `deploy(bytes,bytes)` by `eth_call` with corpus/init_args.fe and arguments that make
  its init code overflow. `deploy` must revert with the init code's Panic;
- calls `version()`, which must return the version in fe0-chain/fe.toml.

It also checks that fe0-chain/Compiler.abi.json, the interface that callers use, is Compiler's
ABI as `fe build` writes it, plus the errors of the phase contracts. Compiler passes those on
without raising them, so `fe build` leaves them out of its ABI. With --write-abi, it writes the
file instead.

It prints the deploy gas of each contract and the gas of the largest compile.
"""
import argparse
import json
import re
import sys
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple, NewType, Self

import web3.contract
from eth_abi.abi import encode as abi_encode
from eth_abi.exceptions import DecodingError
from eth_typing import ABI, ABIError, ChecksumAddress, HexStr, TypeStr
from hexbytes import HexBytes
from web3 import Web3
from web3.contract.contract import ContractFunction
from web3.exceptions import ContractLogicError
from web3.types import TxParams

import cli_check
import embed
import fegen
import sourcify
from embed import FailureMessage
from fegen import FE0, ROOT, Diag, FeName, FeSource, Version, ingot_version
from node import BLOCK_GAS, Gas, Node, corpus

CHAIN: Path = ROOT / "fe0-chain"
OUT: Path = ROOT / "out/chain"
# The module of fe0-chain that declares its contracts, and refers to fe0's modules as `fe0::m`.
LIB: sourcify.SourcePath = sourcify.SourcePath("src/lib.fe")
# A path in fe0-chain's source to a module of fe0, such as `fe0::lexer`.
FE0_MODULE: re.Pattern[str] = re.compile(r"\bfe0::(\w+)")
# A path in fe0's source to another of its own modules, such as `ingot::lexer`.
INGOT_MODULE: re.Pattern[str] = re.compile(r"\bingot::(\w+)")
# The option that writes the committed ABI files instead of checking them.
WRITE_ABI: str = "--write-abi"
# The ingot file of fe0-chain, which holds its version.
MANIFEST: Path = CHAIN / "fe.toml"
# EIP-170 and EIP-3860.
MAX_RUNTIME: int = 24_576
MAX_INITCODE: int = 2 * MAX_RUNTIME
# The program that check_failed_init passes to `deploy`.
INIT_ARGS: Path = embed.CORPUS / "init_args.fe"
# The ABI types of the parameters of INIT_ARGS's init.
INIT_ARGS_TYPES: tuple[TypeStr, ...] = ("uint256", "address", "bool")
# Arguments that make INIT_ARGS's init overflow (corpus/init_args.calls).
OVERFLOWING_ARGS: tuple[int, ChecksumAddress, bool] = (
    2**255, Web3.to_checksum_address((0xbeef).to_bytes(20)), True)


def version() -> Version:
    """Returns the version of fe0-chain that MANIFEST holds (fe0-chain/README.md,
    "Releases")."""
    return ingot_version(MANIFEST)


class CommittedAbi(NamedTuple):
    """A committed file that holds a contract's ABI for callers, which `command` writes from
    the build."""

    path: Path
    command: str

    @staticmethod
    def _text(abi: ABI) -> str:
        return json.dumps(abi, indent=2) + "\n"

    def read(self) -> ABI:
        """Returns the ABI that the file holds. Errors with OSError when there is no such
        file."""
        abi: ABI = json.loads(self.path.read_text())
        return abi

    def write(self, abi: ABI) -> None:
        """Writes `abi` to the file."""
        self.path.write_text(self._text(abi))

    def check(self, abi: ABI) -> list[FailureMessage]:
        """Returns a message when the file does not hold `abi`."""
        if not self.path.exists() or self.path.read_text() != self._text(abi):
            return [FailureMessage(f"{self.path.relative_to(ROOT)} differs from the build;"
                                   f" run {self.command}")]
        return []


# Compiler's ABI for callers, with the errors of the phase contracts (`Builds.interface`).
INTERFACE: CommittedAbi = CommittedAbi(CHAIN / "Compiler.abi.json",
                                       f"tools/chain_check.py {WRITE_ABI}")


class Contract(StrEnum):
    """A contract of fe0-chain. The phases come first."""

    LEXER = "Lexer"
    PARSER = "Parser"
    CHECKER = "Checker"
    BACK = "Back"
    COMPILER = "Compiler"

    @classmethod
    def phases(cls) -> list[Contract]:
        """Returns the phase contracts."""
        return [c for c in cls if c is not cls.COMPILER]

    def id(self) -> sourcify.ContractId:
        """Returns the contract's identifier in `chain_sources`."""
        return sourcify.ContractId(LIB, self)

    def constructor_arg(self) -> str:
        """Returns the name of the argument of Compiler's constructor that takes the phase's
        address, such as "lexer_at"."""
        return f"{self.lower()}_at"


# The code that `fe build` writes to the .bin of a contract.
DeployCode = NewType("DeployCode", bytes)
# The code that creates a contract: its deploy code, then the arguments of its constructor.
Initcode = NewType("Initcode", bytes)


class Code[C: str](NamedTuple):
    """The code of one contract, as `fe build` writes it."""

    contract: C
    deploy_code: DeployCode
    runtime: bytes
    abi: ABI

    @classmethod
    def read(cls, out: Path, contract: C) -> Code[C]:
        """Returns what `fe build` wrote to `out` for `contract`."""
        def text(suffix: str) -> str:
            return (out / f"{contract}{suffix}").read_text()
        def code(suffix: str) -> bytes:
            return bytes.fromhex(text(suffix).strip())
        abi: ABI = json.loads(text(".abi.json"))
        return Code(contract, DeployCode(code(".bin")), code(".runtime.bin"), abi)

    def at(self, w3: Web3, address: ChecksumAddress) -> web3.contract.Contract:
        """Returns the contract at `address` on the chain of `w3`."""
        return w3.eth.contract(address, abi=self.abi)

    def size_line(self) -> str:
        """Returns the line that reports the sizes of the code."""
        return (f"{self.contract}: runtime {len(self.runtime):,} bytes,"
                f" deploy code {len(self.deploy_code):,} bytes")

    def oversize(self) -> list[FailureMessage]:
        """Returns a message for each EIP-170 or EIP-3860 limit that the code exceeds."""
        return [FailureMessage(f"{self.contract}: {what} is {len(code)} bytes, over {limit}")
                for what, code, limit in [("runtime code", self.runtime, MAX_RUNTIME),
                                          ("deploy code", self.deploy_code, MAX_INITCODE)]
                if len(code) > limit]


def chain_sources() -> sourcify.Sources:
    """Returns one ingot that holds fe0-chain's source and the modules of fe0 that fe0-chain
    uses, with fe0-chain's `fe0::` paths rewritten as `ingot::` paths. This ingot is what is
    deployed and verified (docs/adr/0033-verify-on-sourcify.md)."""
    @cache
    def module(name: str) -> FeSource:
        return FeSource((FE0 / module_path(name)).read_text())

    def module_path(name: str) -> sourcify.SourcePath:
        return sourcify.SourcePath(f"src/{name}.fe")

    lib = (CHAIN / LIB).read_text()
    used = fegen.reachable(FE0_MODULE.findall(lib), lambda m: INGOT_MODULE.findall(module(m)))
    files = {LIB: FeSource(FE0_MODULE.sub(r"ingot::\1", lib))}
    files |= {module_path(m): module(m) for m in used}
    return sourcify.Sources(dict(sorted(files.items())))


class Builds(NamedTuple):
    """The code of every contract of fe0-chain, built from `sources`."""

    phases: list[Code[Contract]]
    compiler: Code[Contract]
    sources: sourcify.Sources

    @classmethod
    def build(cls) -> Self:
        """Builds `chain_sources` as Sourcify does and returns the contracts. Exits as
        `fegen.fe_build` does."""
        sources = chain_sources()
        sources.build(OUT)
        return cls([Code.read(OUT, c) for c in Contract.phases()],
                   Code.read(OUT, Contract.COMPILER), sources)

    def all(self) -> list[Code[Contract]]:
        """Returns every contract, the phases first."""
        return [*self.phases, self.compiler]

    def phase_initcode(self) -> dict[Contract, Initcode]:
        """Returns the initcode of each phase contract. A phase's constructor takes no
        arguments."""
        return {b.contract: Initcode(b.deploy_code) for b in self.phases}

    def compiler_initcode(self, phases: Mapping[Contract, ChecksumAddress]) -> Initcode:
        """Returns the initcode of Compiler whose constructor gets the phases at `phases`."""
        factory = Web3().eth.contract(abi=self.interface(), bytecode=self.compiler.deploy_code)
        args = {c.constructor_arg(): a for c, a in phases.items()}
        return Initcode(HexBytes(factory.constructor(**args).data_in_transaction))

    def size_report(self) -> str:
        """Returns the lines that report the sizes of each contract's code."""
        return "\n".join(b.size_line() for b in self.all())

    def oversize(self) -> list[FailureMessage]:
        """Returns a message for each limit that the code of a contract exceeds."""
        return [m for b in self.all() for m in b.oversize()]

    def interface(self) -> ABI:
        """Returns Compiler's ABI with the errors of the phase contracts added, each once."""
        errors: dict[str, ABIError] = {e["name"]: e for b in self.phases for e in b.abi
                                       if e["type"] == "error"}
        return [*self.compiler.abi, *(errors[n] for n in sorted(errors))]


def revert_data(e: ContractLogicError) -> bytes:
    """Returns the revert data of the call that raised `e`."""
    return bytes(HexBytes(HexStr(str(e.data))))


class Compiled(NamedTuple):
    """A `compile(bytes)` call that returned."""

    code: bytes
    gas: Gas


class Reverted(NamedTuple):
    """A `compile(bytes)` call that reverted."""

    revert: bytes
    # The error that the revert data holds, or None when it is not a CompileError.
    diag: Diag | None

    @classmethod
    def of(cls, revert: bytes) -> Self:
        """Returns the revert with data `revert`. Errors as `fegen.CompileError.of_words` does."""
        try:
            failure = fegen.Failure.decode(revert)
        except DecodingError:
            return cls(revert, None)
        return cls(revert, failure.diag if isinstance(failure, fegen.CompileError) else None)

    def describe(self, source: FeSource) -> str:
        """Returns the error in `source` that the call reverted with, or the revert data when it
        is not a CompileError."""
        return self.diag.describe(source) if self.diag else f"revert data {self.revert.hex()}"


# What one `compile(bytes)` call returned.
Outcome = Compiled | Reverted


class Deployed(NamedTuple):
    """A contract that a transaction created."""

    address: ChecksumAddress
    # The gas of the transaction.
    gas: Gas

    @classmethod
    def create(cls, node: Node, initcode: Initcode) -> Self:
        """Deploys `initcode` in a transaction. Errors with RuntimeError when the transaction
        fails or creates no contract."""
        receipt = node.transact({"data": HexBytes(initcode)})
        address = receipt["contractAddress"]
        if address is None:
            raise RuntimeError("the deployment created no contract")
        return cls(address, Gas(receipt["gasUsed"]))


class Counter(NamedTuple):
    """A program that the deploy checks deploy through Compiler, with the start value that its
    constructor takes, and whose `Get` returns that value."""

    path: Path
    start: int

    def source(self) -> FeSource:
        """Returns the program's source."""
        return FeSource(self.path.read_text())

    def args(self) -> bytes:
        """Returns the constructor arguments that the program is deployed with: `start`."""
        return abi_encode(["uint256"], [self.start])

    def get(self, w3: Web3, address: ChecksumAddress) -> CounterGet:
        """Returns what `Get` returns on the program deployed at `address`, called by
        `eth_call`."""
        get = embed.selectors(self.source()).of(FeName("Get")).to_bytes(4)
        got = w3.eth.call({"to": address, "data": HexBytes(get)})
        return CounterGet(self, w3.codec.decode(["uint256"], got)[0])


# corpus/counter.fe, which starts at 2.
COUNTER: Counter = Counter(embed.CORPUS / "counter.fe", 2)


class CounterGet(NamedTuple):
    """What `Get` returns on a `counter` deployed with its `args`."""

    counter: Counter
    value: int

    def failures(self) -> list[FailureMessage]:
        """Returns a message when the value is not the counter's start value."""
        if self.value != self.counter.start:
            return [FailureMessage(f"{self.counter.path.name} deployed by Compiler: Get"
                                   f" returns {self.value}, not {self.counter.start}")]
        return []


class ProgramCheck(NamedTuple):
    """The check of one corpus program on chain."""

    # Relative to ROOT.
    path: Path
    failure: FailureMessage | None
    # The gas of the compile, or 0 when Compiler did not compile the program.
    gas: Gas


@dataclass
class Chain:
    """The compiler, deployed on a node."""

    node: Node
    compiler: web3.contract.Contract
    # The gas of each deployment, by contract.
    deploy_gas: dict[Contract, Gas]

    @classmethod
    def deploy(cls, node: Node, builds: Builds) -> Self:
        """Deploys the phase contracts, then Compiler with their addresses. Errors as
        `Deployed.create` does."""
        phases = {c: Deployed.create(node, code) for c, code in builds.phase_initcode().items()}
        compiler = Deployed.create(node, builds.compiler_initcode(
            {c: d.address for c, d in phases.items()}))
        gas = {c: d.gas for c, d in (phases | {Contract.COMPILER: compiler}).items()}
        return cls(node, node.w3.eth.contract(compiler.address, abi=builds.interface()), gas)

    def gas_report(self) -> str:
        """Returns the lines that report each deployment's gas and their total."""
        lines = [f"deploy {c}: {gas:,} gas" for c, gas in self.deploy_gas.items()]
        lines.append(f"deploy all: {sum(self.deploy_gas.values()):,} gas")
        return "\n".join(lines)

    def _tx(self) -> TxParams:
        return {"from": self.node.accounts[0], "gas": BLOCK_GAS}

    def compile(self, source: FeSource) -> Outcome:
        """Calls `compile(bytes)` with `source`."""
        call = self.compiler.functions.compile(source.encode())
        try:
            code: bytes = call.call(self._tx())
        except ContractLogicError as e:
            return Reverted.of(revert_data(e))
        return Compiled(code, Gas(call.estimate_gas(self._tx())))

    def _deploy_call(self, source: FeSource, args: bytes) -> ContractFunction:
        return self.compiler.functions.deploy(source.encode(), args)

    def deploy_program(self, source: FeSource, args: bytes) -> Deployed:
        """Deploys `source` with `deploy(bytes,bytes)` in a transaction. Errors as
        `Node.transact` does."""
        deploy = self._deploy_call(source, args)
        # The call runs on the same state as the transaction, so it returns the address that the
        # transaction creates.
        address: ChecksumAddress = deploy.call(self._tx())
        receipt = self.node.transact(deploy.build_transaction(self._tx()))
        return Deployed(address, Gas(receipt["gasUsed"]))

    def check_program(self, path: Path) -> ProgramCheck:
        """Returns the check of the corpus program at `path`, relative to ROOT, compiled on chain
        and with the CLI. Its failure is set when the CLI does not compile the program, when
        Compiler reverts, or when the two builds differ."""
        run = cli_check.Run.read(path)
        if not run.compiled():
            failure = FailureMessage(f"{path}: the CLI does not compile it: {run.said()}")
            return ProgramCheck(path, failure, Gas(0))
        match self.compile(run.source):
            case Reverted() as got:
                failure = FailureMessage(f"{path}: Compiler reverts with"
                                         f" {got.describe(run.source)}")
                return ProgramCheck(path, failure, Gas(0))
            case Compiled(code, gas) if code != run.program().code:
                failure = FailureMessage(f"{path}: Compiler's code differs from the CLI's")
                return ProgramCheck(path, failure, gas)
            case Compiled(_, gas):
                return ProgramCheck(path, None, gas)

    def check_reject(self, r: embed.Reject) -> list[FailureMessage]:
        """Compiles the reject program `r` on chain. Returns a message when Compiler does not
        revert with the error of `r`'s header."""
        match self.compile(r.source):
            case Compiled():
                return [FailureMessage(f"{r.path}: Compiler accepts it")]
            case Reverted() as got if got.diag != r.expected:
                return [FailureMessage(f"{r.path}: Compiler gives {got.describe(r.source)},"
                                       f" expected {r.expected.describe(r.source)}")]
            case Reverted():
                return []

    def check_counter(self) -> list[FailureMessage]:
        """Deploys COUNTER through Compiler, and checks that `Get` returns its start value."""
        deployed = self.deploy_program(COUNTER.source(), COUNTER.args())
        print(f"deploy({COUNTER.path.name}): {deployed.gas:,} gas, at {deployed.address}")
        return COUNTER.get(self.node.w3, deployed.address).failures()

    def check_failed_init(self) -> list[FailureMessage]:
        """Returns a message unless `deploy` of INIT_ARGS with OVERFLOWING_ARGS, called by
        `eth_call`, reverts with the init code's Panic."""
        args = self.node.w3.codec.encode(INIT_ARGS_TYPES, OVERFLOWING_ARGS)
        deploy = self._deploy_call(FeSource(INIT_ARGS.read_text()), args)
        what = f"deploy of {INIT_ARGS.name} with an init that overflows"
        try:
            address: ChecksumAddress = deploy.call(self._tx())
        except ContractLogicError as e:
            revert = revert_data(e)
            if fegen.Failure.decode(revert) == fegen.Panicked(fegen.OVERFLOW):
                return []
            return [FailureMessage(f"{what}: reverts with 0x{revert.hex()},"
                                   f" not Panic({fegen.OVERFLOW:#x})")]
        return [FailureMessage(f"{what}: returns {address} instead of reverting")]


def check_version(got: str) -> list[FailureMessage]:
    """Returns a message when `got` differs from `version`. `got` is what Compiler's `version()`
    returned."""
    if got != (want := version()):
        return [FailureMessage(f"Compiler's version() returns {got!r}, but"
                               f" {MANIFEST.relative_to(ROOT)} says {want!r}")]
    return []


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(WRITE_ABI, action="store_true", help=f"write {INTERFACE.path.name}")
    write_abi: bool = ap.parse_args().write_abi
    builds = Builds.build()
    print(builds.size_report())
    failures = builds.oversize()
    if write_abi:
        INTERFACE.write(builds.interface())
    else:
        failures += INTERFACE.check(builds.interface())
    cli_check.build()
    paths = sorted(p.relative_to(ROOT) for p in corpus())
    rejects = embed.load_rejects()
    with Node() as node:
        chain = Chain.deploy(node, builds)
        print(chain.gas_report())
        with ThreadPoolExecutor() as pool:
            programs = list(pool.map(chain.check_program, paths))
            failures += [m for ms in pool.map(chain.check_reject, rejects) for m in ms]
        failures += [p.failure for p in programs if p.failure]
        largest = max(programs, key=lambda p: p.gas)
        print(f"{len(paths)} programs and {len(rejects)} reject programs compiled on chain;"
              f" the most gas: {largest.gas:,} for {largest.path.name}")
        failures += chain.check_counter()
        failures += chain.check_failed_init()
        failures += check_version(chain.compiler.functions.version().call())
    sys.exit("\n".join(failures) or None)


if __name__ == "__main__":
    main()
