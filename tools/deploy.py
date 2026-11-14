#!/usr/bin/env python3
"""Deploy the compiler on chain (fe0-chain, DESIGN.md §8) to Arbitrum One, and run its demo.

It builds fe0-chain at `-O s`, then deploys the four phase contracts and Compiler. The user
approves each transaction in their browser wallet through browser-web3-signer, so no private key
is in the repo or the shell. Then the demo:

- compiles corpus/counter.fe with `compile(bytes)` by `eth_call`, which costs nothing;
- deploys it with `deploy(bytes,bytes)` in a transaction, with start value 2;
- calls `Get` on the new contract.

Each address goes into deployments/<chain id>.json as soon as its contract is deployed. A run
that stops part way resumes where it stopped, and a run after a full deployment only runs the
demo.

With --rehearse, it does all of this on a local anvil node, which signs for the wallet.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Protocol

from eth_typing import ChecksumAddress, HexStr
from hexbytes import HexBytes
from web3 import HTTPProvider, Web3
from web3.types import TxParams, TxReceipt

from chain_check import COUNTER, START, Build, Builds, Contract, interface
from embed import selectors
from fegen import ROOT, FeName, FeSource
from node import Node

ARBITRUM_ONE: int = 42161
ARBITRUM_RPC: str = "https://arb1.arbitrum.io/rpc"
DEPLOYMENTS: Path = ROOT / "deployments"
SIGNER: str = "browser-web3-signer"


class Sender(Protocol):
    """Sends transactions on one chain and waits for them."""

    w3: Web3

    def send(self, tx: TxParams) -> TxReceipt:
        """Sends `tx` and returns its receipt. Errors with RuntimeError when the transaction
        fails."""
        ...


class Wallet:
    """Sends each transaction from the user's browser wallet, through browser-web3-signer."""

    def __init__(self, rpc: str, chain_id: int) -> None:
        self.w3 = Web3(HTTPProvider(rpc))
        self.chain_id = chain_id

    def send(self, tx: TxParams) -> TxReceipt:
        """Sends `tx` from the wallet once the user approves it. Errors with RuntimeError when
        the user rejects it or the transaction fails."""
        args = [SIGNER, "--json", "evm", "send-transaction", "--chain", str(self.chain_id),
                "--data", HexBytes(tx.get("data", b"")).to_0x_hex()]
        if "to" in tx:
            args += ["--to", str(tx["to"])]
        r = subprocess.run(args, stdout=subprocess.PIPE, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"{SIGNER} exited with status {r.returncode}")
        sent = json.loads(r.stdout)
        print(f"  sent {sent['txHash']} {sent.get('explorer') or ''}", flush=True)
        receipt = self.w3.eth.wait_for_transaction_receipt(HexStr(sent["txHash"]), timeout=600)
        if not receipt["status"]:
            raise RuntimeError(f"the transaction {sent['txHash']} failed")
        return receipt


class Rehearsal:
    """Sends each transaction from the first account of a local anvil node."""

    def __init__(self, node: Node) -> None:
        self.w3 = node.w3
        self.node = node

    def send(self, tx: TxParams) -> TxReceipt:
        """Sends `tx` from the node's first account. Errors as `Node.transact` does."""
        return self.node.transact(tx)


class Deployment:
    """The addresses of fe0-chain's contracts on one chain, kept in a file as they arrive."""

    def __init__(self, path: Path) -> None:
        self.path = path
        saved: dict[str, str] = json.loads(path.read_text()) if path.exists() else {}
        self.addresses: dict[Contract, ChecksumAddress] = {
            Contract(name): Web3.to_checksum_address(a) for name, a in saved.items()}

    def deploy(self, sender: Sender, build: Build, initcode: bytes) -> ChecksumAddress:
        """Returns the address of `build`'s contract, and deploys `initcode` for it first when
        the file has none. Errors as `Sender.send` does, or with RuntimeError when the
        transaction creates no contract."""
        if build.contract in self.addresses:
            print(f"{build.contract}: deployed at {self.addresses[build.contract]}")
            return self.addresses[build.contract]
        print(f"{build.contract}: approve its deployment ({len(build.runtime):,} runtime bytes)",
              flush=True)
        receipt = sender.send({"data": HexBytes(initcode)})
        address = receipt["contractAddress"]
        if address is None:
            raise RuntimeError(f"the deployment of {build.contract} created no contract")
        print(f"{build.contract}: deployed at {address}, {receipt['gasUsed']:,} gas", flush=True)
        self.addresses[build.contract] = address
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps({str(c): a for c, a in self.addresses.items()},
                                        indent=2) + "\n")
        return address

    def deploy_all(self, sender: Sender, builds: Builds) -> ChecksumAddress:
        """Deploys each contract that is not deployed yet, the phases first, and returns
        Compiler's address. Errors as `deploy` does."""
        phases = {b.contract.constructor_arg(): self.deploy(sender, b, b.initcode)
                  for b in builds.phases}
        factory = sender.w3.eth.contract(abi=interface(), bytecode=builds.compiler.initcode)
        initcode = HexBytes(factory.constructor(**phases).data_in_transaction)
        return self.deploy(sender, builds.compiler, initcode)


def demo(sender: Sender, compiler: ChecksumAddress) -> None:
    """Compiles COUNTER on chain, deploys it with START through Compiler, and calls `Get`.
    Errors with RuntimeError when `Get` does not return START, or as `Sender.send` does."""
    w3 = sender.w3
    contract = w3.eth.contract(compiler, abi=interface())
    source = FeSource(COUNTER.read_text())
    code: bytes = contract.functions.compile(source.encode()).call()
    print(f"compile({COUNTER.name}) by eth_call: {len(code):,} bytes of deploy code")
    deploy = contract.functions.deploy(source.encode(), w3.codec.encode(["uint256"], [START]))
    # The call runs on the same state as the transaction, as long as nobody else deploys through
    # Compiler in between, so it returns the address that the transaction creates.
    address: ChecksumAddress = deploy.call()
    print(f"deploy({COUNTER.name}): approve the transaction", flush=True)
    receipt = sender.send({"to": compiler, "data": HexBytes(deploy._encode_transaction_data())})
    get = selectors(source)[FeName("Get")].to_bytes(4)
    value = w3.codec.decode(["uint256"], w3.eth.call({"to": address, "data": HexBytes(get)}))[0]
    print(f"{COUNTER.name}: deployed at {address}, {receipt['gasUsed']:,} gas; Get returns {value}")
    if value != START:
        raise RuntimeError(f"Get returns {value}, not {START}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rehearse", action="store_true", help="deploy on a local anvil node")
    ap.add_argument("--rpc", default=ARBITRUM_RPC, help="the chain's JSON-RPC URL")
    ap.add_argument("--chain", type=int, default=ARBITRUM_ONE, help="the chain id")
    args = ap.parse_args()
    builds = Builds.build()
    if failures := builds.oversize():
        sys.exit("\n".join(failures))
    try:
        if args.rehearse:
            with Node() as node:
                sender: Sender = Rehearsal(node)
                deployment = Deployment(ROOT / "out/rehearsal.json")
                deployment.path.unlink(missing_ok=True)
                demo(sender, deployment.deploy_all(sender, builds))
        else:
            sender = Wallet(args.rpc, args.chain)
            if sender.w3.eth.chain_id != args.chain:
                sys.exit(f"{args.rpc} serves chain {sender.w3.eth.chain_id}, not {args.chain}")
            deployment = Deployment(DEPLOYMENTS / f"{args.chain}.json")
            demo(sender, deployment.deploy_all(sender, builds))
    except RuntimeError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
