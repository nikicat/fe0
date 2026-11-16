#!/usr/bin/env python3
"""Generate fe0/src/codegen_tests.fe and format it with fe fmt.

Each program is written once below, and gen_codegen_tests.py puts its text into the module
twice: as Fe code for the official compiler and as a string literal for Fe0. DESIGN.md §10
describes how a differential test compares the two builds.

All the programs share one module, so each contract and msg needs its own name. The names
start with `Cg`.

usage: [FE=path/to/fe] gen_codegen_tests.py
"""
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from fegen import (CHAIN_LEN, FE0, MAX, MAX_DEPTH, Call, CallCase, Case, CaseNumber, Cases, Deploy,
                   DiffTest, ExtraBytes, FeCode, FeLine, FeName, FeSource, Selector, TestName, Wei, Word,
                   difftest_use, lines, source, write_formatted)


@dataclass(frozen=True)
class Variant:
    """A msg variant: its selector, its name, and what its declaration says after the name."""

    selector: Selector
    name: FeName
    rest: FeCode = FeCode("")

    @property
    def declaration(self) -> FeCode:
        return FeCode(self.name + self.rest)


class SelectorFormat(Enum):
    """How a msg block writes its selectors: the format spec of each value."""

    DECIMAL = "d"
    HEX = "#x"


@dataclass(frozen=True)
class Msg:
    """A msg block. Each variant is written once here, with its selector."""

    name: FeName
    variants: tuple[Variant, ...]
    format: SelectorFormat = SelectorFormat.DECIMAL

    @property
    def source(self) -> FeSource:
        return FeSource(f"msg {self.name} {{\n"
                        + "".join(f"    #[selector = {v.selector:{self.format.value}}]\n"
                                  f"    {v.declaration},\n" for v in self.variants)
                        + "}\n")

    def call(self, variant: str, *words: Word, extra: ExtraBytes = ExtraBytes(0),
             value: Wei = Wei(0)) -> Call:
        """A call to the variant named `variant`. Errors when the msg has no such variant."""
        for v in self.variants:
            if v.name == variant:
                return Call(v.selector, *words, extra=extra, value=value)
        raise KeyError(f"{self.name} has no variant {variant}")


COUNTER_MSG = Msg(FeName("CgCounterMsg"), (
    Variant(Selector(0xd09de08a), FeName("Increment"), FeCode(" {}")),
    Variant(Selector(0x6d4ce63c), FeName("Get"), FeCode(" -> u256")),
), SelectorFormat.HEX)
COUNTER = FeSource(COUNTER_MSG.source + """
contract CgCounter {
    mut count: u256,

    init() uses (mut count) {
        count = 0
    }

    recv CgCounterMsg {
        Increment {} uses (mut count) {
            count += 1
        }
        Get {} -> u256 uses (count) {
            count
        }
    }
}
""")


@dataclass(frozen=True)
class Field:
    """A field of a msg variant."""

    name: FeName
    ty: FeCode

    @property
    def declaration(self) -> FeCode:
        return FeCode(f"{self.name}: {self.ty}")


@dataclass(frozen=True)
class Arm:
    """One message variant of CgOps and the recv arm that handles it."""

    name: FeName
    fields: tuple[Field, ...]
    ret: FeCode | None
    body: FeCode  # unindented; ops_program indents it
    uses: FeCode = FeCode("")

    @property
    def arrow(self) -> FeCode:
        return FeCode(f" -> {self.ret}" if self.ret else "")

    def variant(self, selector: Selector) -> Variant:
        """The variant as the msg block declares it, with `selector`."""
        fields = ", ".join(f.declaration for f in self.fields)
        rest = f" {{ {fields} }}{self.arrow}" if self.fields else self.arrow
        return Variant(selector, self.name, FeCode(rest))

    @property
    def pattern(self) -> FeCode:
        return FeCode("{ " + ", ".join(f.name for f in self.fields) + " }" if self.fields else "{}")

    @property
    def handler(self) -> FeCode:
        """The recv arm, indented to sit inside the contract."""
        uses = f" uses ({self.uses})" if self.uses else ""
        return FeCode(f"        {self.name} {self.pattern}{self.arrow}{uses} {{\n"
                      + textwrap.indent(self.body, 12 * " ") + "\n        }")


U256 = FeCode("u256")
BOOL = FeCode("bool")
ADDRESS = FeCode("Address")


A = (Field(FeName("a"), U256),)
AB = (Field(FeName("a"), U256), Field(FeName("b"), U256))
N = (Field(FeName("n"), U256),)
OPS_ARMS = [
    Arm(FeName("Add"), AB, U256, FeCode("a + b")),
    Arm(FeName("Sub"), AB, U256, FeCode("a - b")),
    Arm(FeName("Mul"), AB, U256, FeCode("a * b")),
    Arm(FeName("Div"), AB, U256, FeCode("a / b")),
    Arm(FeName("Mod"), AB, U256, FeCode("a % b")),
    Arm(FeName("Shl"), AB, U256, FeCode("a << b")),
    Arm(FeName("Shr"), AB, U256, FeCode("a >> b")),
    Arm(FeName("Bits"), AB, U256, FeCode("(a & b) | (a ^ b) | ~a")),
    Arm(FeName("Cmp"), AB, U256, FeCode("flags(a < b, a <= b, a > b, a >= b, a == b, a != b)")),
    Arm(FeName("Logic"), (Field(FeName("a"), BOOL), Field(FeName("b"), BOOL)), BOOL,
        FeCode("(a && !b) || (!a && b)")),
    Arm(FeName("Short"), (Field(FeName("a"), BOOL), Field(FeName("b"), U256)), BOOL,
        FeCode("(a || 1 / b == 0) && (!a || b == 0 || 1 / b == 0 || true)")),
    Arm(FeName("Fact"), N, U256, FeCode("fact(n)")),
    Arm(FeName("Sum"), N, U256, FeCode("sum_odd(n)")),
    Arm(FeName("Early"), A, U256, FeCode("early(a) + early(a)")),
    Arm(FeName("Order"), A, U256, FeCode("1 / a + (a - 1)")),
    Arm(FeName("Args"), A, U256, FeCode("pair(p: 1 / a, q: a - 1)")),
    Arm(FeName("Assert"), A, None, FeCode("assert!(a != 0)")),
    Arm(FeName("AssertMsg"), A, None, FeCode('assert!(a != 0, "a is zero")')),
    Arm(FeName("AssertEmpty"), A, None, FeCode('assert!(a != 0, "")')),
    Arm(FeName("Aug"), AB, U256, FeCode("aug(a, b)")),
    Arm(FeName("Chain"), A, U256,
        FeCode("if a == 0 { 10 } else if a == 1 { 11 } else if a == 2 { 12 } else { 13 }")),
    Arm(FeName("Store"),
        (Field(FeName("a"), U256), Field(FeName("b"), BOOL), Field(FeName("c"), ADDRESS)), None,
        FeCode("x = a\nflag = b\nwho = c"), uses=FeCode("mut x, mut flag, mut who")),
    Arm(FeName("LoadX"), (), U256, FeCode("x"), uses=FeCode("x")),
    Arm(FeName("LoadFlag"), (), BOOL, FeCode("flag"), uses=FeCode("flag")),
    Arm(FeName("LoadWho"), (), ADDRESS, FeCode("who"), uses=FeCode("who")),
    Arm(FeName("Same"), (Field(FeName("a"), ADDRESS), Field(FeName("b"), ADDRESS)), BOOL,
        FeCode("a == b")),
    Arm(FeName("Swap"), AB, U256, FeCode("{\n    let t = a\n    x = b\n    return t\n}"),
        uses=FeCode("mut x")),
    Arm(FeName("Bump"), (), U256, FeCode("x = bump_x(x)\nx"), uses=FeCode("mut x")),
]
# Each arm's selector is its position in OPS_ARMS, counted from 1.
OPS_MSG = Msg(FeName("CgOpsMsg"),
              tuple(arm.variant(Selector(n)) for n, arm in enumerate(OPS_ARMS, start=1)))


def op(name: str, *words: Word, extra: ExtraBytes = ExtraBytes(0), value: Wei = Wei(0)) -> Call:
    """A call to the CgOps arm `name`."""
    return OPS_MSG.call(name, *words, extra=extra, value=value)


OPS_FNS = FeSource("""const TEN: u256 = 10

fn flags(_ a: bool, _ b: bool, _ c: bool, _ d: bool, _ e: bool, _ f: bool) -> u256 {
    var r: u256 = 0
    if a { r |= 1 }
    if b { r |= 2 }
    if c { r |= 4 }
    if d { r |= 8 }
    if e { r |= 16 }
    if f { r |= 32 }
    r
}

fn fact(_ n: u256) -> u256 {
    if n == 0 { 1 } else { n * fact(n - 1) }
}

// The sum of the odd numbers up to `n`, with `break` and `continue`.
fn sum_odd(_ n: u256) -> u256 {
    var i: u256 = 0
    var s: u256 = 0
    while true {
        i += 1
        if i > n { break }
        if i % 2 == 0 { continue }
        s += i
    }
    s
}

// Returns early from inside an operand, while `1` is pending on the stack.
fn early(_ a: u256) -> u256 {
    1 + {
        if a == 0 { return 100 }
        a
    }
}

fn pair(p: u256, q: u256) -> u256 {
    p * TEN + q
}

fn aug(_ a: u256, _ b: u256) -> u256 {
    var v = a
    v += b
    v *= 2
    v -= 1
    v /= 3
    v %= 1000
    v <<= 2
    v >>= 1
    v |= 1
    v &= 0xff
    v ^= 3
    v
}

fn bump_x(_ v: u256) -> u256 {
    v + 1
}
""")



def ops_program() -> FeSource:
    arms = "\n".join(arm.handler for arm in OPS_ARMS)
    return FeSource(OPS_MSG.source + "\n" + OPS_FNS
                    + "\ncontract CgOps {\n    mut x: u256,\n    mut flag: bool,\n"
                    "    mut who: Address,\n\n    recv CgOpsMsg {\n" + arms + "\n    }\n}\n")


def ops_calls() -> list[Call]:
    c: list[Call] = []
    one, two, seven = Word(1), Word(2), Word(7)
    for a, b in [(two, Word(3)), (MAX, one), (MAX, Word(0)), (one, MAX), (seven, seven)]:
        c += [op("Add", a, b), op("Sub", a, b), op("Sub", b, a), op("Mul", a, b), op("Div", a, b),
              op("Mod", a, b), op("Bits", a, b), op("Cmp", a, b), op("Cmp", b, a), op("Aug", a, b)]
    c += [op("Mul", Word(0), MAX), op("Mul", Word(1 << 128), Word(1 << 128)),
          op("Mul", Word(1 << 127), Word(1 << 128)),
          op("Div", seven, Word(0)), op("Mod", seven, Word(0)), op("Mod", seven, Word(3))]
    c += [op("Shl", Word(3), Word(255)), op("Shl", one, Word(256)), op("Shr", MAX, Word(300)),
          op("Shr", MAX, Word(4))]
    c += [op("Logic", Word(a), Word(b)) for a in (0, 1) for b in (0, 1)]
    c += [op("Logic", two, Word(0)), op("Logic", Word(0), two)]
    c += [op("Short", one, Word(0)), op("Short", Word(0), Word(0)), op("Short", Word(0), one)]
    c += [op("Fact", Word(n)) for n in (0, 1, 5, 57, 58)]
    c += [op("Sum", Word(n)) for n in (0, 1, 10)]
    c += [op("Early", Word(0)), op("Early", Word(5)), op("Order", Word(0)), op("Args", Word(0)),
          op("Args", two)]
    c += [op("Assert", Word(0)), op("Assert", one), op("AssertMsg", Word(0)), op("AssertMsg", one),
          op("AssertEmpty", Word(0))]
    c += [op("Chain", Word(n)) for n in range(4)]
    c += [op("LoadX"), op("Store", Word(5), one, CC), op("LoadX"), op("LoadFlag"), op("LoadWho"),
          op("Store", Word(6), two, CC), op("Store", Word(6), Word(0), Word((1 << 160) | 0xcc)),
          op("LoadX"), op("Swap", one, two), op("LoadX"), op("Bump"), op("Bump"), op("LoadX")]
    c += [op("Same", CC, CC), op("Same", CC, Word(0xdd)), op("Same", Word(1 << 160), Word(0))]
    # Short calldata, extra bytes and value.
    c += [op("Add", one), op("Add", one, two, extra=ExtraBytes(3)), op("LoadX", value=Wei(5)),
          op("LoadX", extra=ExtraBytes(1))]
    return c


INIT_MSG = Msg(FeName("CgInitMsg"), (
    Variant(Selector(1), FeName("Get"), FeCode(" -> u256")),
    Variant(Selector(2), FeName("Flag"), FeCode(" -> bool")),
    Variant(Selector(3), FeName("Who"), FeCode(" -> Address")),
))
INIT = FeSource(INIT_MSG.source + """
contract CgInit {
    mut a: u256,
    mut b: bool,
    mut c: Address,

    init(x: u256, y: bool, z: Address) uses (mut a, mut b, mut c) {
        a = x
        b = y
        c = z
    }

    recv CgInitMsg {
        Get {} -> u256 uses (a) {
            a
        }
        Flag {} -> bool uses (b) {
            b
        }
        Who {} -> Address uses (c) {
            c
        }
    }
}
""")

MISC_MSG = Msg(FeName("CgMiscMsg"), (
    Variant(Selector(1), FeName("Unit"), FeCode(" { a: u256 } -> u256")),
    Variant(Selector(2), FeName("Pending"), FeCode(" { a: u256 } -> u256")),
    Variant(Selector(3), FeName("Deep"), FeCode(" { n: u256 } -> u256")),
    Variant(Selector(4), FeName("Who"), FeCode(" { a: Address, b: Address } -> Address")),
    Variant(Selector(5), FeName("Long"), FeCode(" { a: u256 }")),
    Variant(Selector(6), FeName("Shadow"), FeCode(" { a: u256 } -> u256")),
    Variant(Selector(7), FeName("Flag"), FeCode(" {} -> bool")),
))
MISC = FeSource(MISC_MSG.source + """
const ON: bool = true
const BIG: u256 = 1 << 255

// A unit function that returns early, and one that returns a unit call.
fn bump(_ a: u256) {
    if a == 0 { return }
    assert!(a != 7)
}

fn bump_twice(_ a: u256) {
    bump(a)
    return bump(a + 1)
}

fn deep(_ n: u256) -> u256 {
    if n == 0 { 0 } else { 1 + deep(n - 1) }
}

fn pick(_ c: bool, _ a: Address, _ b: Address) -> Address {
    if c { a } else { b }
}

contract CgMisc {
    mut count: u256,

    recv CgMiscMsg {
        Unit { a } -> u256 uses (mut count) {
            bump_twice(a)
            count += 1
            count
        }
        Pending { a } -> u256 {
            var i: u256 = 0
            let r = 1 + {
                while true {
                    i += 1
                    if i >= a { break }
                    if i == 100 { return 7 }
                }
                i * 2
            }
            r + BIG / BIG
        }
        Deep { n: m } -> u256 {
            deep(m)
        }
        Who { a, b } -> Address {
            pick(ON, a, b) == pick(!ON, b, a)
            pick(a == b, a, b)
        }
        Long { a } {
            assert!(a == 0, "abcdefghijklmnopqrstuvwxyz01234")
        }
        Shadow { a } -> u256 {
            let x = a
            let y = {
                let x = x + 1
                x * 2
            }
            x + y
        }
        Flag {} -> bool {
            ON
        }
    }
}
""")

NO_RECV = FeSource("""contract CgNoRecv {
    mut n: u256,
}
""")
# The last branch of CgChain holds the deepest nesting that the parser accepts inside an arm.
# One more level of either kind fails with P_TOO_DEEP. The arm, the `if`, its `else` block and
# the expression take ARM_LEVELS. The parentheses are the left operand of a `+`, and each takes
# one level. The blocks are its right operand, which takes one more level, and each block takes
# two, as parser_tests.fe says.
ARM_LEVELS = 4
DEEPEST_PARENS_IN_ARM = MAX_DEPTH - ARM_LEVELS
DEEPEST_BLOCKS_IN_ARM = (MAX_DEPTH - ARM_LEVELS - 1) // 2
CHAIN_MSG = Msg(FeName("CgChainMsg"),
                (Variant(Selector(1), FeName("Pick"), FeCode(" { a: u256 } -> u256")),))
CHAIN = FeSource(CHAIN_MSG.source + "\ncontract CgChain {\n"
         "    recv CgChainMsg {\n        Pick { a } -> u256 {\n            "
         + " else ".join(f"if a == {k} {{ {k} }}" for k in range(CHAIN_LEN))
         + " else { " + "(" * DEEPEST_PARENS_IN_ARM + "a" + ")" * DEEPEST_PARENS_IN_ARM
         + " + " + "{ " * DEEPEST_BLOCKS_IN_ARM + "1" + " }" * DEEPEST_BLOCKS_IN_ARM + " }\n        }\n    }\n}\n")


# The case number of the main deployment. Smaller numbers name the other deployments, in order
# from 1, and larger numbers name the calls. The revert data of a failed test shows the case in
# hex, where 0x1003 is the third call.
MAIN_CASE = CaseNumber(0x1000)


# Words that the calls of several programs send.
AA, CC = Word(0xaa), Word(0xcc)


def program(test: TestName, contract: FeName, program: FeSource, calls: Sequence[Call],
            deploys: Sequence[Deploy] = (), main: Deploy = Deploy()) -> DiffTest:
    """Returns the differential test `test` of `program`, whose contract is `contract`. It sends
    the program `calls` and `deploys`, numbered around MAIN_CASE."""
    cases = Cases(Case(MAIN_CASE, main),
                  [Case(CaseNumber(n), d) for n, d in enumerate(deploys, start=1)],
                  [CallCase(Case(CaseNumber(n), c)) for n, c in enumerate(calls, start=MAIN_CASE + 1)])
    return DiffTest(test, contract, program, cases)


PROGRAMS = [
    program(TestName("counter"), FeName("CgCounter"), COUNTER,
            [COUNTER_MSG.call("Get"), COUNTER_MSG.call("Increment"), COUNTER_MSG.call("Increment"),
             COUNTER_MSG.call("Get"), COUNTER_MSG.call("Increment", value=Wei(1)),
             COUNTER_MSG.call("Get", Word(5))],
            deploys=[Deploy(value=Wei(5)), Deploy(extra=ExtraBytes(1))]),
    program(TestName("ops"), FeName("CgOps"), ops_program(), ops_calls()),
    program(TestName("init"), FeName("CgInit"), INIT,
            [INIT_MSG.call("Get"), INIT_MSG.call("Flag"), INIT_MSG.call("Who")],
            deploys=[Deploy(), Deploy(AA, Word(1)), Deploy(AA, Word(2), CC),
                     Deploy(AA, Word(1), Word((1 << 200) | 0xcc)),
                     Deploy(AA, Word(1), CC, extra=ExtraBytes(7)),
                     Deploy(AA, Word(1), CC, value=Wei(5))],
            main=Deploy(AA, Word(1), CC)),
    program(TestName("misc"), FeName("CgMisc"), MISC,
            [MISC_MSG.call("Unit", Word(a)) for a in (0, 1, 6, 7, 9)]
            + [MISC_MSG.call("Pending", Word(a)) for a in (0, 5, 150)]
            + [MISC_MSG.call("Deep", Word(0)), MISC_MSG.call("Deep", Word(300)),
               MISC_MSG.call("Who", AA, Word(0xbb)), MISC_MSG.call("Who", AA, AA),
               MISC_MSG.call("Long", Word(0)), MISC_MSG.call("Long", Word(1)),
               MISC_MSG.call("Shadow", Word(4)), MISC_MSG.call("Flag")]),
    program(TestName("chain"), FeName("CgChain"), CHAIN,
            [CHAIN_MSG.call("Pick", Word(k))
             for k in (0, 1, CHAIN_LEN // 2, CHAIN_LEN - 1, CHAIN_LEN, CHAIN_LEN + 1)]),
    program(TestName("no_recv"), FeName("CgNoRecv"), NO_RECV, [Call(Selector(1))],
            deploys=[Deploy(Word(5))]),
]


PRELUDE = FeSource("""// Generated by tools/gen_codegen_tests.py. Edit the programs there and rerun it.
// Differential tests of code generation, which DESIGN.md §10 describes.
// They need the EVM. docs/WORKAROUNDS.md explains the attribute below.
#![cfg(target = "evm")]

use ingot::diag::{Diag, G_NO_CONTRACT, T_MISMATCH}
""" + difftest_use("ingot") + """
use ingot::lexer::Pos
use std::abi::DynString
""")

ERRORS = FeSource("""
fn fails(_ s: own DynString) -> Diag {
    let out = difftest::compiled(s)
    assert!(out.code.len() == 0)
    out.err.unwrap()
}

#[test]
fn errors() {
    let d = fails("fn f() -> u256 { 1 }")
    assert!(d.code == G_NO_CONTRACT)
    // An earlier phase's error is passed on.
    let d = fails("contract C {}\\nfn f() -> u256 { true }")
    assert!(d.code == T_MISMATCH && d.pos() == Pos::at(29))
}
""")



def main() -> None:
    out = lines(PRELUDE)
    for p in PROGRAMS:
        out += [FeLine("")] + lines(p.source)
    for p in PROGRAMS:
        out += p.lines()
    out += lines(ERRORS)
    write_formatted(FE0 / "src/codegen_tests.fe", source(out))


main()
