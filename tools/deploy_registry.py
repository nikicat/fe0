#!/usr/bin/env python3
"""Deploy the registries (registry/, docs/adr/0031-deployment-registry.md and
docs/adr/0034-compiler-registry.md) to Arbitrum One, verify them on Sourcify, and run the demo.

It builds registry/ as Sourcify rebuilds it (docs/adr/0033-verify-on-sourcify.md). It creates
CompilerRegistry, with the wallet's account as its admin, and Registry, which checks that
CompilerRegistry lists a compiler, through CreateX in one transaction. Their addresses depend
only on their code and the admin (docs/adr/0028-one-transaction-deploy.md). Then it submits
their source to Sourcify and waits for the matches. The user approves each transaction in
their browser wallet through browser-web3-signer, so no private key is in the repo or the
shell. Then the demo:

- adds the chain's Compiler, which deployments/<chain id>.json records, to CompilerRegistry,
  unless it lists it;
- deploys corpus/counter.fe through Registry with start value 2 and the salt
  keccak256("fe0 registry demo"). A rerun reaches the same contract and creates nothing.

deployments/registry/<chain id>.json records the version, the admin, the addresses and
Sourcify's matches. Errors when the file holds other addresses. Remove the file to deploy this
build.

With --rehearse, it does all of this on a local anvil node, which signs for the wallet, and
skips Sourcify. It deploys fe0-chain there first, and copies the code of Multicall3 and CreateX
to the node from the chain at --rpc.
"""
import sys
from collections.abc import Callable
from contextlib import ExitStack
from functools import partial
from pathlib import Path
from typing import NamedTuple

from eth_typing import ChecksumAddress
from eth_utils.crypto import keccak
from web3.contract.contract import Contract as Web3Contract

from chain_check import Builds, CounterGet, counter_args, counter_source
from deploy import (DEPLOYMENTS, REHEARSAL, Address, ChainId, Deployment, DeploymentRecord,
                    JsonRecord, Plan, Rehearsal, Sender, Url, Wallet, deploy_parser, send)
from fegen import ROOT, Version
from registry_check import Deployment as RegistryDeployment
from registry_check import Name, RegistryBuilds, Salt, version
from sourcify import Match, Sources

# The salt of the demo's deployment.
DEMO_SALT: Salt = Salt(keccak(b"fe0 registry demo"))
# The record of the registries in a rehearsal.
REGISTRY_REHEARSAL: Path = ROOT / "out/rehearsal-registry.json"

# Verifies the registries from the source files at their addresses, and returns their matches.
Verifier = Callable[[Sources, dict[Name, ChecksumAddress]], dict[Name, Match]]


class RegistryRecord(JsonRecord):
    """The registries deployed on one chain, as their file records them."""

    version: Version
    admin: Address
    contracts: dict[Name, Address]
    sourcify: dict[Name, Match]

    @staticmethod
    def file(chain_id: ChainId) -> Path:
        """Returns the file that records the registries on the chain `chain_id`."""
        return DEPLOYMENTS / "registry" / f"{chain_id}.json"


def verify_all(chain_id: ChainId, sources: Sources,
               addresses: dict[Name, ChecksumAddress]) -> dict[Name, Match]:
    """Submits each registry at `addresses` on the chain `chain_id` to Sourcify, and returns
    their matches. Errors as `Sources.verify` does."""
    matches = {}
    for n, address in addresses.items():
        matches[n] = sources.verify(chain_id, address, n.id())
        print(f"Sourcify, {n}: {matches[n]}", flush=True)
    return matches


def skip_sourcify(_sources: Sources, _addresses: dict[Name, ChecksumAddress]
                  ) -> dict[Name, Match]:
    """Returns no match: Sourcify cannot see a rehearsal's node."""
    return {}


class Target(NamedTuple):
    """Where the registries go."""

    sender: Sender
    compiler: ChecksumAddress
    record: Path
    verify: Verifier


def rehearsal_target(stack: ExitStack, rpc: Url) -> Target:
    """Starts a node that `stack` stops and deploys fe0-chain on it. Returns the node as the
    target. Errors as `Rehearsal.start` and `Deployment.deploy_all` do."""
    sender = Rehearsal.start(stack, rpc)
    compiler = Deployment.open(REHEARSAL, Plan.of(Builds.build())).deploy_all(sender)
    REGISTRY_REHEARSAL.unlink(missing_ok=True)
    return Target(sender, compiler, REGISTRY_REHEARSAL, skip_sourcify)


def chain_target(rpc: Url, chain_id: ChainId) -> Target:
    """Returns the chain `chain_id` at `rpc` as the target, with the Compiler that
    deployments/<chain id>.json records. Errors as `Wallet` and `DeploymentRecord.on` do."""
    compiler = DeploymentRecord.on(chain_id).compiler
    return Target(Wallet(rpc, chain_id), compiler, RegistryRecord.file(chain_id),
                  partial(verify_all, chain_id))


def demo(sender: Sender, compilers: Web3Contract, registry: Web3Contract,
         compiler: ChecksumAddress) -> None:
    """Adds `compiler` to `compilers` unless it lists it, and deploys corpus/counter.fe through
    `registry` with that compiler. Errors with RuntimeError when a registry's version()
    differs from registry/fe.toml or the counter's Get returns another value than its start
    value, or as `Sender.send` does."""
    w3 = sender.w3
    want = version()
    for got in (compilers.functions.version().call(), registry.functions.version().call()):
        if got != want:
            raise RuntimeError(f"a registry's version() returns {got!r}, not {want!r}")
    if not compilers.functions.isListed(compiler).call():
        send(sender, compilers.functions.add(compiler), f"add({compiler})")
    deploy = registry.functions.deploy(compiler, DEMO_SALT, counter_source().encode(),
                                       counter_args(w3))
    # The address depends only on the init code and the salt (docs/adr/0031, "Deploying").
    deployment = RegistryDeployment(*deploy.call({"from": sender.account()}))
    send(sender, deploy, "deploy(counter.fe)")
    got = CounterGet.call(w3, deployment.addr)
    print(f"counter.fe: at {deployment.addr}; Get returns {got.value}")
    if failures := got.failures():
        raise RuntimeError("\n".join(failures))


def main() -> None:
    args = deploy_parser(__doc__).parse_args()
    builds = RegistryBuilds.build()
    if failures := builds.failures():
        sys.exit("\n".join(failures))
    try:
        with ExitStack() as stack:
            target = (rehearsal_target(stack, args.rpc) if args.rehearse
                      else chain_target(args.rpc, args.chain))
            admin = target.sender.account()
            plan = builds.plan(admin)
            addresses = plan.addresses
            if target.record.exists():
                plan.check_record(target.record, RegistryRecord.read(target.record).contracts)
            plan.deploy(target.sender)
            matches = target.verify(builds.sources, addresses)
            RegistryRecord(version=version(), admin=admin, contracts=addresses,
                           sourcify=matches).write(target.record)
            w3 = target.sender.w3
            demo(target.sender, builds.compilers.at(w3, addresses[Name.COMPILERS]),
                 builds.registry.at(w3, addresses[Name.REGISTRY]), target.compiler)
    except RuntimeError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
