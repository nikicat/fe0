---
status: todo
tags: [tools]
---
# A contract writer in tools/gen.py

## Goal
`Gen.program()` passes the contract's storage `fields` down to `msgs`, `variant`, `contract`,
`arm` and `uses`, and `msgs` passes the set of `used` selectors to `variant`. Give these
methods one receiver that holds `fields`: a `ContractWriter(gen, fields)`, shaped like the
existing `BodyWriter(gen, body, sc)`. Done when no `Gen` method takes `fields`, and
`python3 tools/gen.py -n 25` gives the same programs for the same seeds as before.
