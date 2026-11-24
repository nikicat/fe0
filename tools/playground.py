#!/usr/bin/env python3
"""Writes playground/src/config.ts, the page's configuration from the repository
(docs/adr/0032, "Configuration")."""
import json
from typing import TypedDict

from eth_typing import ABI, ChecksumAddress

from chain_check import INTERFACE
from compile_on_chain import messages
from deploy import ARBITRUM, CREATEX, Chain, DeploymentRecord
from deploy_registry import RegistryRecord
from embed import CORPUS
from fegen import ROOT, ChainId, FeSource, Url
from registry_check import Name
from sourcify import contract_page

CONFIG = ROOT / "playground/src/config.ts"
# The chains that the page knows, by id.
CHAINS: dict[ChainId, Chain] = {ARBITRUM["id"]: ARBITRUM}
# The example that the page opens with.
START: str = "counter"
# The repository, which the page links for its docs.
REPO: Url = Url("https://github.com/nikicat/fe0")


class Message(TypedDict):
    code: str
    text: str


class Verified(TypedDict):
    address: ChecksumAddress
    sourcify: Url


class Deployed(TypedDict):
    chain: Chain
    compiler: Verified
    registry: Verified


class Config(TypedDict):
    """The `config` of config.ts. The TS types in playground/src/domain/config.ts own the docs
    of the TypedDicts here, and tsc checks the written value against them."""

    repo: Url
    deployments: list[Deployed]
    createx: ChecksumAddress
    messages: dict[str, Message]
    examples: dict[str, FeSource]
    start: str


def verified(chain_id: ChainId, address: ChecksumAddress) -> Verified:
    """Returns `address` on the chain `chain_id`, with its page on Sourcify."""
    return Verified(address=address, sourcify=contract_page(chain_id, address))


def deployments() -> list[Deployed]:
    """Returns the chain, Compiler and Registry of each deployment that deployments/ records.
    Errors with RuntimeError when a deployment is on a chain that CHAINS lacks, or as
    `DeploymentRecord.chain_ids` and `DeployedRecord.on` do, such as when
    deployments/registry/ lacks the chain."""
    found = []
    for chain_id in DeploymentRecord.chain_ids():
        chain = CHAINS.get(chain_id)
        if chain is None:
            raise RuntimeError(f"deployments/ records chain {chain_id}, which CHAINS lacks")
        compiler = DeploymentRecord.on(chain_id).compiler
        registry = RegistryRecord.on(chain_id).registry
        found.append(Deployed(chain=chain, compiler=verified(chain_id, compiler),
                              registry=verified(chain_id, registry)))
    return found


def config() -> Config:
    """Returns the page's configuration. Errors with RuntimeError when corpus/ lacks the
    example START, or as `deployments` does."""
    examples = {p.stem: FeSource(p.read_text()) for p in sorted(CORPUS.glob("*.fe"))}
    if START not in examples:
        raise RuntimeError(f"corpus/ has no {START}.fe, the example that the page opens with")
    return Config(repo=REPO, deployments=deployments(), createx=CREATEX.address,
                  messages={str(code.value()): Message(code=str(code), text=text)
                            for code, text in messages().items()},
                  examples=examples, start=START)


def config_ts(page: Config, *, compiler: ABI, registry: ABI) -> str:
    """Returns the text of config.ts. The interfaces are `as const`, so that viem types the
    calls of Compiler and Registry from them."""
    return ("// Written by tools/playground.py. Do not edit.\n"
            'import { branded } from "./domain/config";\n\n'
            f"export const compilerAbi = {json.dumps(compiler, indent=1)} as const;\n\n"
            f"export const registryAbi = {json.dumps(registry, indent=1)} as const;\n\n"
            f"export const config = branded({json.dumps(page, indent=1)});\n")


def main() -> None:
    CONFIG.write_text(config_ts(config(), compiler=INTERFACE.read(),
                                registry=Name.REGISTRY.interface().read()))
    print(f"wrote {CONFIG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
