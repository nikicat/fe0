# 31. A registry of programs deployed through any Compiler

- Date: 2026-11-22
- Status: proposed

## Context
`Compiler.deploy(src, args)` compiles a Fe0 program and creates it in one transaction
(fe0-chain/README.md). Nothing records what it created, so a contract deployed this way cannot
be found later with its source. The playground (playground/README.md) builds call forms from a
program's source. With the source of a deployed contract, it could show the contract's name,
version, source and constructor arguments, and call it as it calls one it deployed itself.

Each release of fe0-chain is a new Compiler, at its own address. A Compiler's address depends
only on its release's code ([0028](0028-one-transaction-deploy.md)), so anyone can check which
release an address holds by building that release's tag.

## Decision
A new contract, the registry, deploys programs and records them. It lives in its own ingot,
with its own version and its own release tags, so that the five contracts of fe0-chain do not
change. It is written in Fe, since Fe0 has no `bytes`. It is immutable.

**Deploying.** `deploy(compiler, salt, label, src, args) -> (contract, created)` takes the
Compiler and a salt that the deployer chooses:
1. It calls `compiler.compile(src)` with `STATICCALL`, so the compiler cannot change any state.
   It errors with the compiler's revert data, such as `CompileError`, when the compile fails.
2. It appends `args` to the deploy code that `compile` returns, and the result is the init
   code. The address is the one at which CreateX's `deployCreate2` creates the init code with
   `keccak256(salt)` ([0028](0028-one-transaction-deploy.md)).
3. When that address has no code, it creates the contract through CreateX, and `created` is
   true. It errors with the init code's revert data when no contract is created, as
   `Compiler.deploy` does.
4. When the address already has code, it creates nothing, and `created` is false.
5. When the address has no record yet, it writes one, emits `Deployed`, and adds `label`. When
   it has one, it only adds `label`.

The address depends only on the init code and the salt. It does not depend on the caller or on
the registry, so it is the same for every deployer, under every version of the registry, and on
every chain that has CreateX. A deployer who wants a new instance, or an address of a chosen
form, picks another salt. The registry passes CreateX `keccak256(salt)`, not `salt`. CreateX
mixes the caller or the chain id into a salt that starts with the caller's address or with 20
zero bytes, and a hash does not start with either, so CreateX only hashes it again.

A contract at that address started from exactly this init code, since a `CREATE2` address
commits to it. So a contract that someone created first, through the registry or through
CreateX directly, is the same contract: a Fe0 constructor sees no value and no block data, and
its caller is always CreateX. Its state may have changed since. `created` is false, so the
caller knows that the contract existed before.

**Labels.** A contract has any number of labels. The `deploy` that writes its record adds the
first. Each later `deploy` that reaches the same address, and each call of
`label(contract, text)`, adds a label from its caller, like a bookmark. A label never replaces
another. `label` errors when the contract has no record.

**Creator.** The creator is the caller of the `deploy` that created the contract. A contract
that was created outside the registry and recorded later has no creator in its record, since
the registry did not see the creation. Its first label names who recorded it.

**Checking.** Anyone can check a record with the source, the args and the salt from its
`Deployed` event. `compile(src)` on the record's compiler, by `eth_call`, gives the deploy code,
and with `args` the init code. The contract's address must be the one that CreateX gives for
that init code and `keccak256(salt)`. The compile trusts the compiler, which is why a client
checks which compiler a record names.

**Compilers.** `addCompiler(compiler)` is open to anyone. It records the address and emits
`CompilerAdded(compiler, version)`, with the version that `compiler.version()` returns.
`deploy` takes any compiler, listed or not; the list is for finding compilers. The registry
does not decide which compilers to trust. A client trusts a compiler when its address
is one that a release of fe0-chain deploys to, which each release's `deployments/` files
record.

**Where each fact is kept:**

| Fact | Where |
|---|---|
| The contract's address, the compiler, the creator | Topics of the `Deployed` event |
| `keccak256(src)`, the salt, `src`, `args` | Data of the `Deployed` event |
| The contract's address and the labeller, with the label as data | The `Labeled` event |
| The block of the `Deployed` event, the compiler, the creator and `keccak256(src)`, for each recorded contract | State: `info[contract]` |
| The labeller and the block of the `Labeled` event, for each label of a contract | State: `labels[contract][j]`, with its count |
| The number of recorded contracts, and the address at each index | State: `count`, `at[i]` |
| The contracts that each account created or labelled, and those of each compiler | State: one list for each, with its count |
| The compilers | State: `compilers[i]`; the `CompilerAdded` event gives each one's version |

The creator and a labeller are the account that calls the registry (`msg.sender`), which may be
a smart wallet. The blocks in state are those of the registry's events, which a client fetches
with `eth_getLogs`.

Some facts are not stored:
- The contract's name comes from its source.
- The contract's version comes from its `version()`, when it has one, by `eth_call`.
- The gas used and the time of the deployment come from the transaction's receipt and block.

Keeping the source in event data depends on Fe emitting an event with `bytes` fields (Open
questions).

**Reading.** A client lists contracts from the state, a page of `eth_call`s at a time. For one
contract, it reads `info[contract]` and `labels[contract]`, then the `Deployed` and `Labeled`
events with `eth_getLogs` over the blocks that those name. Public RPC endpoints limit the block
range of `eth_getLogs`, so a client cannot scan the chain's whole history for the events.

## Alternatives
- **The registry runs `CREATE2` itself:** only the registry could then create a contract at its
  addresses, but each version of the registry would give a program a different address.
- **`CREATE`:** each call would make a new instance at a new address, so the same program could
  not be found by its code, and no address could be known before the transaction.
- **A salt that includes the caller:** the same contract would get a different address for each
  deployer, though it is the same code with the same arguments.
- **One label for each contract:** a later deployer's label would be lost, or would replace
  the creator's.
- **One registry for each Compiler:** each release would need a new registry, and a client
  would read one for each release.
- **An upgradeable registry with a compiler that its admin sets:** the admin could replace the
  code that reads and writes the records. Logs cannot change, but state can. With the compiler
  as an argument, a new release needs no upgrade.
- **Call `compiler.deploy`:** a compiler could return an address that it did not create, or
  call back into the registry. Compiling with `STATICCALL` and creating through CreateX removes
  both.
- **A list of compilers that an owner keeps:** it needs an admin key. A Compiler's address
  already identifies its release, so a client can decide.
- **Read the source from the transaction's calldata:** the calldata is `deploy(…)` only when
  an account calls the registry directly. A call through a smart wallet, an ERC-4337 bundle,
  Multicall3 or another contract hides it, and public RPC endpoints have no trace API to find
  it.
- **Store the source in state:** a new storage slot costs about 20,000 gas for 32 bytes. Log
  data costs 8 gas a byte, so a source of 1 to 8 KB adds 8,000 to 64,000 gas to a deployment
  of about 2.1M.

## Consequences
- The registry is deployed through CreateX, as fe0-chain is
  ([0028](0028-one-transaction-deploy.md)), so it has one address on every chain.
- A deployment that creates a contract writes about seven new storage slots and updates four
  counts, about 175,000 gas, and the events. `info` packs its four fields into three slots,
  and `at[i]`, the label, the creator's list and the compiler's list take one each. A label
  writes about two slots and updates two counts.
- A `deploy` that reaches an existing contract still pays for the compile, since the registry
  needs the init code to find the address. `label` does not compile.
- A program's constructor sees CreateX as its caller, not the deployer. `Compiler.deploy` has
  the same limit, with Compiler as the caller.
- The registry needs CreateX on its chain, as fe0-chain does.
- The playground lists the registry's contracts and opens each one with its source, labels,
  constructor arguments and compiler. It marks the compilers of known releases.

## Open questions
- Whether Fe 26.7.0 can emit an event with `bytes` fields, and at what cost in code size.
- Whether to support search by name, through `keccak256(name)` in state, or leave it to the
  client over the list.
- How a program's constructor could see the deployer as its caller.
