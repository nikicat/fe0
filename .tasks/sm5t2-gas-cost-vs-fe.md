---
status: doing
tags: [codegen, gas]
---
# Measure the gas cost of Fe0's output against Fe's

## Goal
ADR 0007 keeps every local, parameter and return address in a memory frame, and accepts that
Fe0's output costs more gas than Fe's ("the harness compares behaviour, not size"). Nobody has
measured how much more. Done means a table of gas per call, Fe0 against Fe at `-O 1` and
`-O s`, for the corpus and for workloads shaped like the contracts people deploy, and a
decision, written into ADR 0007 or a new ADR, on whether the frame design stays.

## Decisions
- Measure inside the differential harness. `Deployed.call` (`fe0/src/difftest.fe`, about line
  237) already calls both builds with the same `CALL_GAS`. Reading `evm.gas()` before and after
  each `try_call_raw` gives the gas of each call. The call overhead is the same for both builds,
  so the difference is their code.
- Fe0 cannot express an ERC20 token or a Uniswap pool. It has no `StorageMap`, no events, no
  way to construct an `Address` or read the caller, no sized integers and no external calls
  (SPEC.md §2, §3.3). So measure the closest shapes it has:
  - storage-heavy, like an ERC20 `transfer`: `tokens.fe` (three fixed holders), `vault.fe`,
    `escrow.fe`, `auction.fe`, `voting.fe`;
  - compute-heavy, like a pool's price math: `isqrt.fe`, `power.fe`, `primes.fe`,
    `collatz.fe`, and a new program with a mulDiv-style chain of checked arithmetic;
  - call-heavy: `fib.fe`, `ackermann.fe`, `many_params.fe`.
- Expectation to check, not a result: a storage-bound call such as a token transfer spends
  most of its gas on `SLOAD` and `SSTORE` (2,100 to 22,100 gas each), which both builds pay
  alike, so Fe0's frame overhead should be a few percent there. In compute- and call-heavy code,
  each local read costs about 15 gas (`PUSH1 0x40 MLOAD PUSHn off ADD MLOAD`) against 3 for a
  `DUP`, and each call stores three or more words, so the ratio there could be several times.

## Options if the cost is too high
- Keep FP on the stack instead of at `0x40`, which saves the `PUSH1 0x40 MLOAD` (6 gas) on every
  local access.
- Keep a leaf function's locals on the stack when it has at most 16 live values.
- A peephole pass in the assembler, for example to drop a store followed by a load of the same
  slot.
- Each costs bytes in the phase contracts, which must stay under 24,576 (ADR 0014). Measure
  CompileProbe's size with each one.

## State
`tools/gas_compare.py` measures it (Nov 12). It deploys Fe0's build and Fe's builds at `-O 1`
and `-O s` of each corpus program on anvil (Cancun), sends the call script, and counts the
gas each call's code spends (gasUsed less the same transaction to an address with no code).
Run it with `FE=<patched fe> uv run --project tools tools/gas_compare.py [--calls]`. Fe0's gas over Fe's,
summed over each program's calls:

- Storage-bound (tokens, vault, escrow, auction, counter, ring, toggle, messages, two_msgs,
  init_args, rate_limit, units, xorshift, voting, no_init, owner): 1.00 to 1.08. `tokens.fe`,
  the closest to an ERC20 transfer: 1.01. Voting, no_init and owner were 1.2 to 1.4 until Fe0
  packed storage as Fe does (Trcr1j): they had paid for extra `SSTORE`s.
- Mixed (arith, dispatch, logic): 1.3 to 1.4.
- Compute-bound (loops, primes, isqrt, power, bitcount, digits, collatz, factorial, sums,
  reverse_bits, parity, gcd): 2.0 to 3.7.
- Call-bound (fib, ackermann, many_params): 2.0 to 3.1.
- The whole corpus: 1.75 against `-O 1`, 1.71 against `-O s` (1.81 and 1.76 before packing).

- `amm.fe` (added Nov 12), a Uniswap v2–style pair without the tokens: 1.07. A swap costs
  about 12,450 gas against 11,500. Two `SSTORE`s and their cold `SLOAD`s make up about
  10,000 of each, so Fe0's arithmetic costs about 1.6 times Fe's but adds only 8% to the
  swap. A real pair also calls two token contracts, so its ratio would be lower still.

So the frame design costs little where storage dominates, as in a token or a pool's swap, and two to three
times where arithmetic, loops and calls dominate, as in an AMM's price math.

## Next
1. Decide, with the user, whether to change the frame design, and when. The cheapest option
   is FP kept on the stack (saves 6 of the about 15 gas of each local access); measure it
   with this tool and CompileProbe's size.
2. Optional: a mulDiv-style program, for 512-bit price math in the compute group.
3. Write the result into ADR 0007's consequences and the submission write-up.
