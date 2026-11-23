"""Builds Fe contracts the way Sourcify rebuilds them, and verifies them on Sourcify
(docs/adr/0033-verify-on-sourcify.md). Sourcify's APIv2 is documented at
https://sourcify.dev/server/api-docs/."""
import shutil
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import Any, Literal, NamedTuple, NewType, Self

import requests
from eth_typing import ChecksumAddress
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic.alias_generators import to_camel

import fegen
from deploy import ChainId, Url
from fegen import FeSource

API: str = "https://sourcify.dev/server"
# Sourcify's repository, whose pages show a contract and whether Sourcify verified it.
REPO: str = "https://repo.sourcify.dev"
# How long to wait for a verification job, in seconds, and how often to ask.
TIMEOUT: float = 300
POLL: float = 5
# The fe.toml that Sourcify writes beside the source files it rebuilds.
MANIFEST: str = '[ingot]\nname = "sourcify_verification"\nversion = "0.1.0"\n'

# The path of a source file from the ingot's directory, such as "src/lib.fe".
SourcePath = NewType("SourcePath", str)


class Match(StrEnum):
    """How Sourcify says the chain's code matches the rebuilt code."""

    MATCH = "match"
    EXACT = "exact_match"


class ContractId(NamedTuple):
    """Sourcify names a contract by the file that declares it and its name
    (contractIdentifier in APIv2)."""

    path: SourcePath
    name: str

    def __str__(self) -> str:
        return f"{self.path}:{self.name}"


class _Reply(BaseModel):
    """A JSON body that Sourcify's API replies with. Its keys are in camelCase."""

    model_config = ConfigDict(alias_generator=to_camel, frozen=True)


class _Accepted(_Reply):
    verification_id: str


class _JobError(_Reply):
    custom_code: str
    message: str


class _Contract(_Reply):
    """A contract as Sourcify reports it, with no match when it verified none."""

    match: Match | None

    def found(self) -> Match:
        """Returns the match. Errors with RuntimeError when Sourcify found none."""
        if self.match is None:
            raise RuntimeError("Sourcify found no match")
        return self.match


class _Job(_Reply):
    is_job_completed: bool
    error: _JobError | None = None
    contract: _Contract


def contract_page(chain_id: ChainId, address: ChecksumAddress) -> Url:
    """Returns the page of REPO that shows the contract at `address` on the chain `chain_id`."""
    return Url(f"{REPO}/{chain_id}/{address}")


def _request[R: _Reply](method: Literal["GET", "POST"], path: str, reply: type[R],
                        body: dict[str, Any] | None = None) -> R:
    """Returns Sourcify's reply to `method` on `path`. Errors with requests.HTTPError on a
    status of 400 or more, or with RuntimeError when the reply is not a `reply`."""
    r = requests.request(method, f"{API}{path}", json=body, timeout=60,
                         headers={"User-Agent": "fe0-tools"})
    r.raise_for_status()
    try:
        return reply.model_validate_json(r.content)
    except ValidationError as e:
        raise RuntimeError(f"Sourcify's reply to {method} {path} is not {reply.__name__}: {e}"
                           ) from e


def _known_match(chain_id: ChainId, address: ChecksumAddress) -> Match:
    """Returns the match that Sourcify recorded for the contract at `address`. Errors as
    `_request` does, or as `_Contract.found` does."""
    return _request("GET", f"/v2/contract/{chain_id}/{address}", _Contract).found()


def _await_job(job: str) -> Match:
    """Waits for the verification job `job` and returns its match. Errors with RuntimeError
    when the job fails, finds no match or does not finish within TIMEOUT."""
    def done() -> _Job | None:
        status = _request("GET", f"/v2/verify/{job}", _Job)
        return status if status.is_job_completed else None
    try:
        status = fegen.poll(done, TIMEOUT, POLL)
    except TimeoutError as e:
        raise RuntimeError(f"Sourcify did not finish the verification {job} in {TIMEOUT} s"
                           ) from e
    if status.error is not None:
        raise RuntimeError(f"Sourcify: {status.error.custom_code}: {status.error.message}")
    return status.contract.found()


class Sources(NamedTuple):
    """The `.fe` files under the `src/` of an ingot, as Sourcify takes them."""

    files: dict[SourcePath, FeSource]

    @classmethod
    def read(cls, ingot: Path) -> Self:
        """Returns the source files of `ingot`."""
        return cls({SourcePath(p.relative_to(ingot).as_posix()): FeSource(p.read_text())
                    for p in sorted((ingot / "src").rglob("*.fe"))})

    def build(self, ingot: Path, out: Path) -> None:
        """Makes the directory `ingot` hold only the files and MANIFEST, and builds it into
        `out` with no options, as Sourcify does. Exits as `fegen.fe_build` does."""
        shutil.rmtree(ingot, ignore_errors=True)
        for path, text in self.files.items():
            (ingot / path).parent.mkdir(parents=True, exist_ok=True)
            (ingot / path).write_text(text)
        (ingot / "fe.toml").write_text(MANIFEST)
        fegen.fe_build(ingot, out)

    def verify(self, chain_id: ChainId, address: ChecksumAddress,
               contract: ContractId) -> Match:
        """Submits the files for `contract` at `address`, waits for Sourcify's verdict, and
        returns the match. Returns the recorded match of a contract that Sourcify verified
        before. Errors with RuntimeError when Sourcify refuses the submission, finds no match,
        or does not finish within TIMEOUT."""
        try:
            accepted = _request("POST", f"/v2/verify/{chain_id}/{address}", _Accepted,
                                self._submission(contract))
        except requests.HTTPError as e:
            if e.response.status_code != HTTPStatus.CONFLICT:
                raise RuntimeError(f"Sourcify refused the verification: {e.response.text}"
                                   ) from e
            # Sourcify verified the contract before.
            return _known_match(chain_id, address)
        return _await_job(accepted.verification_id)

    def _submission(self, contract: ContractId) -> dict[str, Any]:
        """Returns the body of the request that verifies `contract` from the files."""
        return {"stdJsonInput": {"language": "Fe", "settings": {},
                                 "sources": {p: {"content": t} for p, t in self.files.items()}},
                "compilerVersion": fegen.fe_version(), "contractIdentifier": str(contract)}
