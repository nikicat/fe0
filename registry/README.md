# registry: programs deployed through a listed Compiler

Two contracts. Registry deploys programs written in Fe0, the subset of Fe that this repository
compiles, and records them with their source and the accounts that asked for them.
CompilerRegistry holds the list of Compilers that Registry accepts. An admin keeps the list. A
Compiler is the contract of `fe0-chain/` that compiles Fe0 on chain, and each release of
fe0-chain is a new one. [ADR 0031](../docs/adr/0031-deployment-registry.md) and
[ADR 0034](../docs/adr/0034-compiler-registry.md) give the design.

## Interface

`Registry.abi.json` and `CompilerRegistry.abi.json` are the ABIs. The docs of the contracts
in `src/` say what each function does. In Solidity terms:

```solidity
struct AddressPage { uint256 total; address[] items; }

interface ICompilerRegistry {
    error NotAdmin(address caller);
    error NotPendingAdmin(address caller);
    error Listed(address compiler);
    error NotListed(address compiler);

    event CompilerAdded(address indexed compiler, string version);
    event CompilerRemoved(address indexed compiler);
    event AdminChanged(address indexed previous, address indexed admin);

    // constructor(address admin)

    function add(address compiler) external;
    function remove(address compiler) external;
    function isListed(address compiler) external view returns (bool);
    function compilers(uint256 start, uint256 limit) external view
        returns (AddressPage memory);

    function admin() external view returns (address);
    function pendingAdmin() external view returns (address);
    function transferAdmin(address to) external;
    function acceptAdmin() external;

    function version() external pure returns (string memory);
}

interface IRegistry {
    struct Record { uint64 registered_block; address compiler; bytes32 src_hash; }
    struct Deployment { address addr; bool created; }

    error UnlistedCompiler(address compiler);

    event Registered(address indexed addr, address indexed compiler, bytes32 src_hash,
                     bytes32 salt, bytes src, bytes args);

    // constructor(address compiler_registry)

    function deploy(address compiler, bytes32 salt, bytes calldata src, bytes calldata args)
        external returns (Deployment memory);

    function compilerRegistry() external view returns (address);
    function info(address addr) external view returns (Record memory);
    function contracts(uint256 start, uint256 limit) external view
        returns (AddressPage memory);
    function contractsOf(address account, uint256 start, uint256 limit) external view
        returns (AddressPage memory);

    function version() external pure returns (string memory);
}
```

## Versions and verification

`registry/fe.toml` makes `registry/` an ingot of the workspace, and holds the version that both
contracts' `version()` returns. To make a new version, raise it there and in `VERSION` in
`src/lib.fe`. `tools/registry_check.py` fails when they differ.

Sourcify verifies both contracts against their source. `tools/registry_check.py` and
`tools/deploy_registry.py` build them from `src/` the way Sourcify rebuilds Fe source, not with
`registry/fe.toml`, so that the bytecode matches
([ADR 0033](../docs/adr/0033-verify-on-sourcify.md)).

## Build and check

```sh
uv run --project tools tools/registry_check.py
```

This checks both contracts on a local anvil node, with fe0-chain's Compiler, against the
rules of ADR 0031 and ADR 0034 that its `--help` lists. It needs network access to Arbitrum
One's RPC endpoint, for CreateX's code. It fails when `Registry.abi.json` or
`CompilerRegistry.abi.json` differs from the build. Run it with `--write-abi` to write them.

## Deployed

On Arbitrum One, as `deployments/registry/42161.json` records them:

| | Address |
|---|---|
| CompilerRegistry | [`0x60a377ac44Bd4Df3EbEDC104f92B959d0Adc9273`](https://repo.sourcify.dev/42161/0x60a377ac44Bd4Df3EbEDC104f92B959d0Adc9273) (Sourcify) |
| Registry | [`0x7810A73f714FA9dd628c17BA1013232263a25a4D`](https://repo.sourcify.dev/42161/0x7810A73f714FA9dd628c17BA1013232263a25a4D) (Sourcify) |
| Admin of CompilerRegistry | `0xcbAeA7AF074b46BE5232D20c686419F76C95D1E4` |

## Deploy

```sh
uv run --project tools tools/deploy_registry.py
```

This deploys both contracts on Arbitrum One, with your wallet's account as the admin, and
verifies them on Sourcify. It then adds to CompilerRegistry the Compiler that `tools/deploy.py`
deployed, unless the list has it, and, as a demo, deploys `corpus/counter.fe` through
Registry. You approve each transaction in your browser wallet through browser-web3-signer.
`deployments/registry/<chain id>.json` records the version, the addresses, the admin and
Sourcify's matches. With `--rehearse`, the script does the same on a local anvil node, without
Sourcify. `tools/deploy_registry.py --help` says what it does in full.
