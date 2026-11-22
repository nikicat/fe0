#!/usr/bin/env python3
"""Builds the playground (playground/README.md) into out/playground/."""
import json
import re
import shutil
from typing import TypedDict

from eth_typing import ABI, ChecksumAddress

from chain_check import Contract, committed_interface
from compile_on_chain import messages
from deploy import ARBITRUM, Chain, Deployment, Tag, Url, git
from embed import CORPUS
from fegen import ROOT, FeSource

PAGE = ROOT / "playground"
OUT = ROOT / "out/playground"
# The example that the page opens with.
FIRST_EXAMPLE: str = "counter"


class Message(TypedDict):
    """An error code as the native CLI prints it, such as `N014`, with its message."""

    code: str
    text: str


class Data(TypedDict):
    """The contents of data.json."""

    # The repository on GitHub, for the page's links.
    repo: Url
    chain: Chain
    compiler: ChecksumAddress
    tag: Tag
    abi: ABI
    # The key is an error code's value as `CompileError` holds it, in decimal.
    messages: dict[str, Message]
    examples: dict[str, FeSource]


def repo() -> Url:
    """Returns the GitHub URL of the repository that `origin` names."""
    url = git("remote", "get-url", "origin").removesuffix(".git")
    return Url(re.sub(r"^git@github\.com:", "https://github.com/", url))


def data() -> Data:
    """Returns the contents of data.json. Errors as `Deployment.on` does."""
    deployment = Deployment.on(ARBITRUM["id"])
    examples = {p.stem: FeSource(p.read_text()) for p in sorted(CORPUS.glob("*.fe"))}
    first = {FIRST_EXAMPLE: examples.pop(FIRST_EXAMPLE)}
    return Data(repo=repo(), chain=ARBITRUM,
                compiler=deployment.addresses[Contract.COMPILER],
                tag=deployment.release.tag, abi=committed_interface(),
                messages={str(code.value()): Message(code=str(code), text=text)
                          for code, text in messages().items()},
                examples=first | examples)


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(PAGE, OUT, ignore=shutil.ignore_patterns("*.test.mjs", "README.md"))
    (OUT / "data.json").write_text(json.dumps(data(), indent=1) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
