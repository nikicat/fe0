#!/usr/bin/env python3
"""Compile a Fe0 program with the compiler deployed on Arbitrum One, by a free `eth_call`.

It prints what the native CLI (fe0-cli) prints for the same program: the deploy code as hex on
stdout, or the error on stderr as `<path>:line:col: CODE message`. Like the CLI, it exits with 0
when the program compiles and with 1 when Compiler rejects it.

The on-chain compiler reports only the first error, and no warnings.
"""
import argparse
import re
import sys
from pathlib import Path

from eth_typing import ChecksumAddress
from web3 import HTTPProvider, Web3
from web3.exceptions import ContractLogicError

from chain_check import Contract, Reverted, committed_interface, revert_data
from cli_check import ExitCode
from deploy import ARBITRUM, Deployment, Url
from fegen import FE0, ROOT, DiagCode, FeSource, LineCol

MESSAGES: Path = ROOT / "fe0-cli/src/messages.fe"
# A DiagCode constant of fe0/src/diag.fe, with its value.
DIAG_CODE: re.Pattern[str] = re.compile(r"^pub const (\w+): DiagCode = DiagCode \{ raw: (\d+) \}",
                                        re.M)
# An entry of the CLI's message table.
MESSAGE: re.Pattern[str] = re.compile(r'Message \{ code: (\w+), text: "([^"]*)" \}')


def messages() -> dict[DiagCode, str]:
    """Returns the CLI's message for each error code."""
    codes = {name: DiagCode.of_value(int(value))
             for name, value in DIAG_CODE.findall((FE0 / "src/diag.fe").read_text())}
    return {codes[name]: text for name, text in MESSAGE.findall(MESSAGES.read_text())}


def compiler(chain_id: int) -> ChecksumAddress:
    """Returns the address of Compiler that deployments/<chain id>.json records. Errors as
    `Deployment.on` does, or with KeyError when it records none."""
    return Deployment.on(chain_id).addresses[Contract.COMPILER]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("program", type=Path, help="a Fe0 source file")
    ap.add_argument("--rpc", type=Url, default=ARBITRUM["rpc"], help="the chain's JSON-RPC URL")
    ap.add_argument("--chain", type=int, default=ARBITRUM["id"], help="the chain id")
    args = ap.parse_args()
    source = FeSource(args.program.read_text())
    w3 = Web3(HTTPProvider(args.rpc))
    try:
        contract = w3.eth.contract(compiler(args.chain), abi=committed_interface())
    except RuntimeError as e:
        sys.exit(str(e))
    try:
        code: bytes = contract.functions.compile(source.encode()).call()
    except ContractLogicError as e:
        got = Reverted.of(revert_data(e))
        if got.diag is None:
            sys.exit(f"{args.program}: Compiler reverts with {got.describe(source)}")
        at = LineCol.of(got.diag.offset, source)
        text = messages().get(got.diag.code, "")
        print(f"{args.program}:{at}: {got.diag.code} {text}", file=sys.stderr)
        sys.exit(ExitCode.REJECTED)
    print(code.hex())


if __name__ == "__main__":
    main()
