---
status: todo
deps: [Tbrbh1]
tags: [spec, checker, codegen]
---
# Step 2: `StorageMap` fields

## Goal
ADR 0018. Contract fields of type `StorageMap<K, V>` with `K` in {u256, Address} and `V` in
{u256, bool, Address}, read as `m[k]` and written as `m[k] = v` and with compound assignment.
Slots are hashed as Fe hashes them. Done means SPEC, checker, code generation, a token corpus
program with a balance per account, a probe that pins the slot hashing, and every phase
contract under 24,576 bytes.
