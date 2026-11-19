# 18. `StorageMap` fields

- Date: 2026-11-12
- Status: accepted; step 2 of [0016](0016-steps-toward-real-contracts.md)

## Context
Fe0's storage is a fixed list of fields at fixed slots (SPEC.md §6). A token with three
holders has to name them `b0`, `b1` and `b2` (`corpus/tokens.fe`). Fe keeps per-key state in
`StorageMap<K, V>` fields, whose entries live at hashed slots:

```fe
contract Token uses (ctx: Ctx) {
    mut balances: StorageMap<Address, u256>,

    recv TokenMsg {
        BalanceOf { who } -> u256 uses (balances) {
            balances[who]
        }
        Transfer { to, amount } uses (ctx, mut balances) {
            let from = ctx.caller()
            assert!(balances[from] >= amount, "balance too low")
            balances[from] -= amount
            balances[to] += amount
        }
    }
}
```

## Decision
Fe0 adds `StorageMap<K, V>` as the type of a contract field only:
- `K` and `V` are each `u256`, `bool` or `Address`. Fe writes a `bool` key as the word 0 or 1
  **[✓]**, so it hashes as a `u256` key does and costs nothing extra. Nested maps and tuple
  keys are left out.
- An entry is read as `m[k]` and written as `m[k] = v` and with the compound assignments, in a
  body whose `uses` names `m` (`mut m` to write). The checker types `k` and `v`.
- In `m[k] = v` and `m[k] op= v`, `v` is evaluated before `k`, as in Fe **[✓]** (SPEC §4).
- The parser reads the target of an assignment as an expression, then requires a name or an
  entry. So a place in parentheses, as in `(m[k]) = 1`, is accepted, as Fe accepts it **[✓]**.
- `StorageMap<…>` is accepted only as a field's type, so the generic arguments are read in one
  place and do not open generics in general (SPEC.md §3.2, §3.3).
- Code generation computes each entry's slot the way Fe does, with `KECCAK256` over the key and
  the field's slot. SPEC §6 gives the layout **[✓]**.

Fe also writes `m.get(k)` and `m.set(key: k, value: v)`. Fe0 accepts only the index form, so
that a program reads one way.

## Alternatives
- **Tuple keys** (`StorageMap<(Address, Address), u256>`), as Fe's ERC20 example uses for
  allowances: they need tuple expressions. A nested map or a key built from two words can come
  in a later step.
- **The `get` and `set` methods:** method calls, which Fe0 keeps out ([0017](0017-caller.md)).
- **Other ways to match the word `StorageMap` in `Parser.field`,** which uses
  `at_word(W_STORAGE_MAP)`. On Fe 26.6.0 at `-O s`, comparing the packed spelling inline with
  no helper made ParseProbe 41 bytes larger. Checking only for an identifier and reading the
  word with `expect_word(W_STORAGE_MAP)` in `map_ty` made it 114 bytes larger.

## Consequences
- With step 1, a token can keep a balance per account. `corpus/token.fe` does, with the
  deployer as the only minter. Allowances wait for tuple keys or nested maps, so
  `transferFrom` is not yet expressible.
- Fe's slot hashing is part of the output that must match
  ([0002](0002-match-official-output.md)). The probe `corpus/maps.fe` pins it, and the node
  harness compares the raw storage slots after each call. On a node, Fe0 matches Fe on it at
  `-O 1` and `-O s`.
- Maps cost gas for the hashing in both builds alike, so the ratio to Fe's gas should stay close
  to 1 for map-heavy code.
