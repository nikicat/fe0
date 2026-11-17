---
status: doing
tags: [compiler, size]
---
# Room in the Parser contract

## Goal
The Parser contract has 1,882 bytes left under 24,576 (22,694 on Nov 17), and every syntax gap
in SPEC.md §10 costs Parser bytes. Free room before spending it, in measured steps:
1. Measure the code bytes of each Parser function (`fe build --emit sizes`, `-O s`).
2. Tables instead of code where a function maps tokens to values, as the Lexer's keyword and
   punctuation tables did (7,685 to 6,031 bytes, ADR 0014).
3. Move token-level decisions to the Lexer contract (about 18.5 KB room): bracket matching
   (`after_group`), the newline rules of §3.4, contextual words.
4. Read general forms and let the Checker resolve them, such as any `ctx.NAME()`.
5. An error field instead of `Result<Diag, _>` in the parser's rules, if step 1 shows `Result`
   plumbing is large (ADR 0011 measured 733 to 845 bytes for `parse()` alone).
Done means each step is in with its saving recorded, or dropped with its measured reason.

## Decisions
- Stay on Fe 26.6.0 (ADR 0015). Free room with tables first (step 2). Move to the next Fe
  release that has #1978 when it ships.

## State
Step 1 done (Nov 17, Fe 26.6.0, `-O s`). The Parser's runtime is 22,694 bytes, with 22,054
bytes of code. The largest functions are `item` (2,263), the dispatcher (1,928), `stmt` (947)
and `primary` (787).

The largest cost is not in any one function. Fe clones a function once for each struct
constant passed to it (`__constref_` in the sizes). The Parser has 88 such clones, worth 5,179
bytes. The Checker has 42, worth 1,754 bytes; the Lexer 6 (162 bytes); Back none. The cloned
parameters are `Tok`, `Spelling`, `DiagCode` and the AST's `Kind`.

An experiment made `eat` and `expect` take the raw `u8` code instead of a `Tok`. The Parser
went from 22,694 to 20,977 bytes (-1,717), and its clones dropped to 60. The rest are
`Node` methods (24 clones, 1,344 bytes), `at_word`, `typed`, `attr_start`, `err`,
`braced_list`, `paren_list` and `empty_call`.

Fe master already fixes the clones: 8e3b56924, "Pass one-scalar constants as values"
(argotorg/fe#1978), merged after the 26.6.0 release. `spike-constref/` reproduces it: 12
struct constants passed to one helper give 975 bytes on 26.6.0 and 365 on master (839f3a2e3).
fe0-chain built with master at `-O s`, with no change to our code:

| Contract | 26.6.0 | master |
|---|---|---|
| Lexer | 6,031 | 5,906 |
| Parser | 22,694 | 17,583 |
| Checker | 22,093 | 21,246 |
| Back | 18,079 | 17,769 |
| Compiler | 1,893 | 1,901 |

## Ruled out
- `enum Tok` (Nov 17): no clones, but Fe 26.6.0 has no cast between an enum and an integer.
  The wire code and `==` then need an 81-arm `match` (`wire()`, 1,182 bytes) in every
  contract. Lexer +2,077, Parser +2,519, Checker +2,117, Back +1,774. Requested upstream as
  argotorg/fe#2020 (Nov 17): a cast between a unit-only enum and its variant index.
- A raw `u8` parameter in `eat` and `expect` saves 1,717 Parser bytes, but drops the type at
  every call site. Kept only as a last resort.

## Next
Step 2: tables in the Parser.
