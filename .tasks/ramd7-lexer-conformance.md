---
status: todo
deps: [T0010]
tags: [conformance]
---
# Lexer gaps after the redeploy

## Goal
◐ and ❌ rows of SPEC.md §10 whose fix lives mostly in the Lexer and Back, which have room
(Lexer about 18.5 KB, Back about 7 KB under 24,576). They change the deployed contracts, so
they wait for the submission's redeploy.
- Binary (`0b`) and octal (`0o`) literals, SPEC §1.
- `assert!` messages over 31 bytes: `Error(string)` over several words, §1.
- `init`, `recv`, `assert`, `with` as identifiers, §1. This one costs Parser bytes, which
  are tight (about 1.9 KB left), so measure it first.
