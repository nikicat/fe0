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
- `K` is `u256` or `Address`, and `V` is `u256`, `bool` or `Address`. Nested maps and tuple
  keys are left out.
- An entry is read as `m[k]` and written as `m[k] = v` and with the compound assignments, in a
  body whose `uses` names `m` (`mut m` to write). The checker types `k` and `v`.
- `StorageMap<…>` is accepted only as a field's type, so the generic arguments are read in one
  place and do not open generics in general (SPEC.md §3.2, §3.3).
- Code generation computes each entry's slot the way Fe does, with `KECCAK256` over the key and
  the field's slot. The harness checks this by comparing raw storage slots after each call.

Fe also writes `m.get(k)` and `m.set(key: k, value: v)`. Fe0 accepts only the index form, so
that a program reads one way.

## Alternatives
- **Tuple keys** (`StorageMap<(Address, Address), u256>`), as Fe's ERC20 example uses for
  allowances: they need tuple expressions. A nested map or a key built from two words can come
  in a later step.
- **The `get` and `set` methods:** method calls, which Fe0 keeps out ([0017](0017-caller.md)).

## Consequences
- With step 1, a token can keep a balance per account. Allowances wait for tuple keys or nested
  maps, so `transferFrom` is not yet expressible.
- Fe's slot hashing is now part of the output that must match
  ([0002](0002-match-official-output.md)). A probe in `corpus/` pins it, and the node harness
  compares the slots.
- Maps cost gas for the hashing in both builds alike, so the ratio to Fe's gas should stay close
  to 1 for map-heavy code.

## Update (Nov 12)
- **`bool` keys** are accepted too. Fe writes a `bool` key as the word 0 or 1 **[✓]**, so it
  hashes as a `u256` key does, and it costs nothing extra.
- **Layout.** Fe lays maps out as SPEC §6 says **[✓]**. The probe is `corpus/maps.fe`. On a
  node, Fe0 matches Fe on it at `-O 1` and `-O s`.
- **Evaluation order.** In `m[k] = v` and `m[k] op= v`, Fe evaluates `v` before `k` **[✓]**.
  SPEC §4 now says so, and code generation follows it.
- **Places.** The parser reads the target of an assignment as an expression, then requires a
  name or an entry. So a place in parentheses, as in `(m[k]) = 1`, is accepted. Fe accepts it
  too **[✓]**.
- `corpus/token.fe` keeps a balance per account, with the deployer as the only minter.
- **Size, at `-O s`:** LexProbe stays at 7,141 bytes. ParseProbe goes from 25,448 to 26,328
  bytes (+880), CheckProbe from 41,074 to 42,325 (+1,251) and CompileProbe from 54,641 to
  56,475 (+1,834). In the first version of the parser, the map type cost 515 bytes and `m[k]`
  315.
- `Parser.field` matches the word `StorageMap` with `at_word(W_STORAGE_MAP)`. Two other ways
  were measured at `-O s`, and both made ParseProbe larger. Comparing the packed spelling
  inline in `field`, with no `at_word` helper, added 41 bytes. Checking only for an identifier
  and then reading the word with `expect_word(W_STORAGE_MAP)` in `map_ty` added 114 bytes.
