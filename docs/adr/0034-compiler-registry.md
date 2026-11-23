# 34. An admin keeps the list of compilers that the registry accepts

- Date: 2026-11-23
- Status: accepted

## Context
The registry (ADR 0031) compiles a program with a Compiler of fe0-chain and records it with its
source. A record is only as trustworthy as the compiler that made it: a contract that claims to
compile Fe0 can return any code. Each release of fe0-chain is a new Compiler at a new address,
so the set of trusted compilers grows over time and is not known when the registry is built.

## Decision
A second contract, CompilerRegistry, holds the list of trusted compilers. An admin adds and
removes them. `add` emits the compiler's `version()`, and a compiler is listed at most once.
Registry takes CompilerRegistry's address in its constructor, and its `deploy` errors with
`UnlistedCompiler` when CompilerRegistry does not list the compiler. So every record names a
compiler that the admin trusted when the record was made, and Registry itself has no admin.

The first admin is the account that deploys the two contracts. The deploy tool passes it to
CompilerRegistry's constructor, since CreateX, not the deployer, calls the constructor. The
admin role moves in two steps: the admin names the next admin with `transferAdmin`, and that
account takes the role with `acceptAdmin`. The role is its own component,
`registry/src/admin.fe`, which CompilerRegistry adds through its own `recv AdminMsg` block.
It is ours to write because Fe has no inheritance and its std has no Ownable or AccessControl.
Until Fe0 can compile its own compiler and so check a Compiler on chain, the admin decides
which compilers to trust. Then the role can move to a contract that does that check, and the
list needs no person.

## Alternatives
- **The registry takes any compiler, and the list only helps clients find compilers:** each
  client would have to decide which compilers to trust, and a record would carry nothing
  about trust.
- **Anyone adds a compiler:** the list could fill with contracts that only claim to compile
  Fe0, and it would say nothing about trust.
- **An upgradeable CompilerRegistry:** an upgrade could change the rules for every record that
  is already made. Moving the admin role to a contract gives the same path to a trustless list
  without changing the code. Fe's std has no upgradeable proxy, only `delegatecall` and
  ERC-1167 clones, so the proxy would also be ours to write and verify.
- **The admin in Registry itself:** Registry would need a key for its whole life, though only
  the compiler list needs one.

## Consequences
- The admin's address is part of CompilerRegistry's init code, so both contracts' addresses
  depend on it.
- Removing a compiler stops new deployments through it. Records it made stay.
- A client that trusts the admin knows that each record's compiler was listed when the record
  was made, and `isListed` tells whether it still is. A client that does not trust the admin
  can still check a record against the source (ADR 0031, "Checking").
