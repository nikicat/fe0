#!/usr/bin/env python3
"""Deploy the registries (registry/, docs/adr/0031-deployment-registry.md and
docs/adr/0034-compiler-registry.md) to Arbitrum One, verify them on Sourcify, and run the demo.

It first deploys fe0-chain as tools/deploy.py does, leaving out each contract already on the
chain, so a chain that deploy.py deployed to only gets its record checked and verified again.

It builds registry/ as Sourcify rebuilds it (docs/adr/0033-verify-on-sourcify.md). It creates
CompilerRegistry, with the wallet's account as its admin, and Registry, which checks that
CompilerRegistry lists a compiler, through CreateX in one transaction. Their addresses depend
only on their code and the admin (docs/adr/0028-one-transaction-deploy.md). Then it submits
their source to Sourcify and waits for the matches. The user approves each transaction in
their browser wallet through browser-web3-signer, so no private key is in the repo or the
shell. Then the demo:

- adds fe0-chain's Compiler to CompilerRegistry, unless it lists it;
- deploys corpus/counter.fe through Registry with start value 2 and the salt
  keccak256("fe0 registry demo"). A rerun reaches the same contract and creates nothing.

deployments/registry/<chain id>.json records the version, the admin, the addresses and
Sourcify's matches. Errors when the file holds another version or other addresses. Remove the
file to deploy this build.

With --rehearse, it does all of this on a local anvil node, which signs for the wallet. A
rehearsal skips Sourcify. It copies the code of Multicall3 and CreateX to the node from the
chain at --rpc.
"""
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import ClassVar

from eth_typing import ChecksumAddress
from eth_utils.crypto import keccak
from web3.contract.contract import Contract as Web3Contract

from chain_check import Builds, CounterGet, counter_args, counter_source
from deploy import (DEPLOYMENTS, Address, DeployedRecord, Deployment, Sender, deploy_chain,
                    deploy_parser, open_sender, send)
from fegen import ROOT
from registry_check import Deployment as RegistryDeployment
from registry_check import Name, RegistryBuilds, Salt, version

# The salt of the demo's deployment.
DEMO_SALT: Salt = Salt(keccak(b"fe0 registry demo"))


class RegistryRecord(DeployedRecord[Name]):
    """The registries' record, with CompilerRegistry's first admin
    (docs/adr/0034-compiler-registry.md)."""

    DIR: ClassVar[Path] = DEPLOYMENTS / "registry"
    REHEARSAL: ClassVar[Path] = ROOT / "out/rehearsal-registry.json"

    admin: Address


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
            sender = open_sender(stack, args.rehearse, args.rpc, args.chain)
            compiler = deploy_chain(sender, Builds.build()).compiler
            admin = sender.account()
            path = sender.record_file(RegistryRecord)
            deployment = Deployment.open(path, version(), builds.plan(admin), RegistryRecord)
            addresses = deployment.deploy_all(sender, builds.sources, lambda contracts, matches:
                                              RegistryRecord(version=deployment.version,
                                                             admin=admin, contracts=contracts,
                                                             sourcify=matches)).contracts
            w3 = sender.w3
            demo(sender, builds.compilers.at(w3, addresses[Name.COMPILERS]),
                 builds.registry.at(w3, addresses[Name.REGISTRY]), compiler)
    except RuntimeError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
