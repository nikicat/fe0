#!/usr/bin/env python3
"""Writes playground/src/config.ts, the page's configuration from the repository
(docs/adr/0032, "Configuration")."""
import json
import re
from typing import TypedDict

from eth_typing import ABI, ChecksumAddress

from chain_check import Contract, committed_interface
from compile_on_chain import messages
from deploy import ARBITRUM, Chain, DeploymentRecord, Tag, Url, git
from embed import CORPUS
from fegen import ROOT, FeSource

CONFIG = ROOT / "playground/src/config.ts"
# The chains that the page knows, by id.
CHAINS: dict[int, Chain] = {ARBITRUM["id"]: ARBITRUM}
# The example that the page opens with.
START: str = "counter"


class Message(TypedDict):
    code: str
    text: str


class Deployed(TypedDict):
    chain: Chain
    compiler: ChecksumAddress
    tag: Tag


class Config(TypedDict):
    """The `config` of config.ts. The TS types in playground/src/domain/config.ts own the docs
    of Config, Deployed and Message, and tsc checks the written value against them."""

    repo: Url
    deployments: list[Deployed]
    messages: dict[str, Message]
    examples: dict[str, FeSource]
    start: str


def repo() -> Url:
    """Returns the GitHub URL of the repository that `origin` names."""
    url = git("remote", "get-url", "origin").removesuffix(".git")
    return Url(re.sub(r"^git@github\.com:", "https://github.com/", url))


def deployments() -> list[Deployed]:
    """Returns the chain and Compiler of each deployment that deployments/ records. Errors with
    RuntimeError when a deployment is on a chain that CHAINS lacks, or as
    `DeploymentRecord.chain_ids` and `DeploymentRecord.on` do."""
    found = []
    for chain_id in DeploymentRecord.chain_ids():
        chain = CHAINS.get(chain_id)
        if chain is None:
            raise RuntimeError(f"deployments/ records chain {chain_id}, which CHAINS lacks")
        record = DeploymentRecord.on(chain_id)
        found.append(Deployed(chain=chain, compiler=record.addresses[Contract.COMPILER],
                              tag=record.release.tag))
    return found


def config() -> Config:
    """Returns the page's configuration. Errors with RuntimeError when corpus/ lacks the
    example START, or as `deployments` does."""
    examples = {p.stem: FeSource(p.read_text()) for p in sorted(CORPUS.glob("*.fe"))}
    if START not in examples:
        raise RuntimeError(f"corpus/ has no {START}.fe, the example that the page opens with")
    return Config(repo=repo(), deployments=deployments(),
                  messages={str(code.value()): Message(code=str(code), text=text)
                            for code, text in messages().items()},
                  examples=examples, start=START)


def config_ts(abi: ABI, page: Config) -> str:
    """Returns the text of config.ts. The interface is `as const`, so that viem types the
    calls of Compiler from it."""
    return ("// Written by tools/playground.py. Do not edit.\n"
            'import { branded } from "./domain/config";\n\n'
            f"export const compilerAbi = {json.dumps(abi, indent=1)} as const;\n\n"
            f"export const config = branded({json.dumps(page, indent=1)});\n")


def main() -> None:
    CONFIG.write_text(config_ts(committed_interface(), config()))
    print(f"wrote {CONFIG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
