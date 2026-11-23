# 31. A registry of programs deployed through a listed Compiler

- Date: 2026-11-22
- Status: accepted

## Context
`Compiler.deploy(src, args)` compiles a Fe0 program and creates it in one transaction
(fe0-chain/README.md). Nothing records what it created, so a contract deployed this way cannot
be found later with its source. The playground (playground/README.md) builds call forms from a
program's source. With the source of a deployed contract, it could show the contract's name,
version, source and constructor arguments, and call it as it calls one it deployed itself.

Each release of fe0-chain is a new Compiler, at its own address. A Compiler's address depends
only on its release's code ([0028](0028-one-transaction-deploy.md)).

## Decision
A new contract, the registry, deploys programs and records them. It lives in its own ingot
and has its own version, so that the five contracts of fe0-chain do not change. Sourcify
verifies its source ([0033](0033-verify-on-sourcify.md)). It is written in Fe, since Fe0 has
no `bytes`. It is immutable.

**Deploying.** `deploy(compiler, salt, src, args) -> Deployment { addr, created }` takes the
Compiler and a salt that the deployer chooses. It errors with `UnlistedCompiler` unless the
compiler registry lists the Compiler ([0034](0034-compiler-registry.md)). Then:
1. It calls `compiler.compile(src)` with `STATICCALL`, so the compiler cannot change any state.
   It errors with the compiler's revert data, such as `CompileError`, when the compile fails.
2. It appends `args` to the deploy code that `compile` returns, and the result is the init
   code. The address is the one at which CreateX's `deployCreate2` creates the init code with
   `keccak256(salt)` ([0028](0028-one-transaction-deploy.md)).
3. When that address has no code, it creates the contract through CreateX, and `created` is
   true. It errors with CreateX's `FailedContractCreation` when no contract is created, since
   CreateX does not pass on the init code's revert data. A client finds the reason by an
   `eth_call` that runs the init code.
4. When the address already has code, it creates nothing, and `created` is false.
5. When the address has no record yet, it writes one and emits `Registered`.
6. It adds the contract to the caller's set, once.

The address depends only on the init code and the salt. It does not depend on the caller or on
the registry, so it is the same for every deployer, under every version of the registry, and on
every chain that has CreateX. A deployer who wants a new instance, or an address of a chosen
form, picks another salt.

The registry passes CreateX `keccak256(salt)`, not `salt`, so that CreateX mixes neither the
caller nor the chain id into it. CreateX hashes a salt again, and mixes in nothing else, when
the salt's first 20 bytes are neither the caller's address nor zero. It does the same when they
are zero and the 21st byte is 0x00. Any other salt gets the caller, the chain id or both, or
CreateX rejects it. A hash in practice starts with neither the caller's address nor 20 zero
bytes, so the `CREATE2` salt is `keccak256(keccak256(salt))`.

A contract at that address started from exactly this init code, since a `CREATE2` address
commits to it. So its code is the one that this init code makes. Its state may differ from
the state that this call would make. A Fe0 constructor can read the block and the transaction
and call other contracts, so the same init code can leave a different state. The state may
also have changed since. `created` is false, so the caller knows that the contract existed
before.

**Accounts.** The creator is not part of a contract's code, so the registry records no
creator. A program that needs an owner takes it as a constructor argument: the argument is
part of the init code, so the address commits to it, and the `Registered` event records it.
Every account that calls `deploy` for a contract has it in its set, whether that call created
it or not, the first account and each later one alike. The registry keeps no name or other
text for a contract: its source says what it is.

**Checking.** Anyone can check a record with the source, the args and the salt from its
`Registered` event. `compile(src)` on the record's compiler, by `eth_call`, gives the deploy
code, and with `args` the init code. The contract's address must be the one that CreateX gives
for that init code and `keccak256(salt)`. The compile trusts the compiler, which is why a
client checks which compiler a record names.

**Compilers.** An admin keeps the list of compilers in a separate contract, the compiler
registry ([0034](0034-compiler-registry.md)). The registry takes its address in its
constructor.

**Where each fact is kept:**

| Fact | Where |
|---|---|
| The contract's address, the compiler | Topics of the `Registered` event |
| `keccak256(src)`, the salt, `src`, `args` | Data of the `Registered` event |
| The block of the `Registered` event, the compiler and `keccak256(src)`, for each recorded contract | State: `info[contract]` |
| The recorded contracts, in the order of recording | State: a list |
| The contracts that each account called `deploy` for, each once | State: `by_account`, a set for each account |

The account is the one that calls the registry (`msg.sender`), which may be a smart
wallet.

Some facts are not stored:
- The contract's name comes from its source.
- The contract's version comes from its `version()`, when it has one, by `eth_call`.
- The gas used and the time of the deployment come from the transaction's receipt and block.

**Reading.** Each list in state has a view that returns its length and a page of its items,
so a client lists contracts one `eth_call` per page. For one contract, it reads
`info[contract]`, then the `Registered` event with `eth_getLogs` over the block that it
names. Public RPC endpoints limit the block
range of `eth_getLogs`, so a client cannot scan the chain's whole history for the events.

## Alternatives
- **The registry runs `CREATE2` itself:** only the registry could then create a contract at its
  addresses, but each version of the registry would give a program a different address.
- **`CREATE`:** each call would make a new instance at a new address, so the same program could
  not be found by its code, and no address could be known before the transaction.
- **A salt that includes the caller:** the same contract would get a different address for each
  deployer, though it is the same code with the same arguments.
- **Labels, a text that each deployer adds to a contract:** the source already says what a
  contract is, and each label would cost two storage slots.
- **A creator in each record:** the account that sent the creating transaction is not part of
  the contract's code, and a contract created outside the registry would have none.
- **A list of the contracts of each compiler:** a client finds them from `info` or from the
  `Registered` event's `compiler` topic, and each record would pay for one more slot.
- **One registry for each Compiler:** each release would need a new registry, and a client
  would read one for each release.
- **An upgradeable registry with a compiler that its admin sets:** the admin could replace the
  code that reads and writes the records. Logs cannot change, but state can. With the compiler
  as an argument, a new release needs no upgrade.
- **Call `compiler.deploy`:** a compiler could return an address that it did not create, or
  call back into the registry. Compiling with `STATICCALL` and creating through CreateX removes
  both.
- **Run the init code again with `CREATE` when CreateX fails, to pass on its revert data:**
  the registry would grow for a reason that a client gets from one `eth_call`.
- **Read the source from the transaction's calldata:** the calldata is `deploy(…)` only when
  an account calls the registry directly. A call through a smart wallet, an ERC-4337 bundle,
  Multicall3 or another contract hides it, and public RPC endpoints have no trace API to find
  it.
- **Store the source in state:** a new storage slot costs about 20,000 gas for 32 bytes. Log
  data costs 8 gas a byte, so a source of 1 to 8 KB adds 8,000 to 64,000 gas to a deployment
  of about 2.05M, which is what deploying `corpus/counter.fe` through Compiler costs.

## Consequences
- The registry is deployed through CreateX, as fe0-chain is
  ([0028](0028-one-transaction-deploy.md)), so it has one address on every chain where the
  compiler registry has the same first admin ([0034](0034-compiler-registry.md)).
- A deployment that creates a contract writes five new storage slots and updates two lengths, of
  the list of contracts and of the caller's set, about 120,000 gas, plus the `Registered` event.
  `info` packs its three fields into two slots. The list of contracts takes one, and the
  caller's set takes two.
- A `deploy` that reaches an existing contract still pays for the compile, since the registry
  needs the init code to find the address.
- A program's constructor sees CreateX as its caller, not the deployer. `Compiler.deploy` has
  the same limit, with Compiler as the caller.
- The registry needs CreateX on its chain, as fe0-chain does.
- The playground can list the registry's contracts and open each one with its source,
  constructor arguments and compiler ([0032](0032-playground-architecture.md)). When `deploy`
  fails with `FailedContractCreation`, it can run the init code by `eth_call` to show why the
  constructor reverted.

## Open questions
- Whether to support search by name, through `keccak256(name)` in state, or leave it to the
  client over the list.
- How a program's constructor could see the deployer as its caller.
