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
from dataclasses import dataclass

from fegen import CHAIN_LEN, FE0, MAX, Call, Case, Cases, Deploy, DiffTest, difftest_use, write_formatted


@dataclass(frozen=True)
class Variant:
    """A msg variant: its selector, its name, and what its declaration says after the name."""

    selector: int
    name: str
    rest: str = ""

    @property
    def declaration(self):
        return self.name + self.rest


@dataclass(frozen=True)
class Msg:
    """A msg block. Each variant is written once here, with its selector."""

    name: str
    variants: tuple[Variant, ...]
    spec: str = "d"  # the format spec the selectors are written with

    @property
    def source(self):
        return (f"msg {self.name} {{\n"
                + "".join(f"    #[selector = {v.selector:{self.spec}}]\n    {v.declaration},\n"
                          for v in self.variants)
                + "}\n")

    def call(self, variant, *words, **kw):
        """A call to the variant named `variant`."""
        return Call(next(v.selector for v in self.variants if v.name == variant), *words, **kw)


COUNTER_MSG = Msg("CgCounterMsg", (
    Variant(0xd09de08a, "Increment", " {}"),
    Variant(0x6d4ce63c, "Get", " -> u256"),
), spec="#x")
COUNTER = COUNTER_MSG.source + """
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
"""


@dataclass(frozen=True)
class Field:
    """A field of a msg variant."""

    name: str
    ty: str

    @property
    def declaration(self):
        return f"{self.name}: {self.ty}"


@dataclass(frozen=True)
class Arm:
    """One message variant of CgOps and the recv arm that handles it."""

    name: str
    fields: tuple[Field, ...]
    ret: str | None
    body: str  # unindented; ops_program indents it
    uses: str = ""

    @property
    def selector(self):
        """The variant's selector: its position in OPS_ARMS, counted from 1."""
        return OPS_ARMS.index(self) + 1

    @property
    def arrow(self):
        return f" -> {self.ret}" if self.ret else ""

    @property
    def variant(self):
        """The variant as the msg block declares it."""
        fields = ", ".join(f.declaration for f in self.fields)
        rest = f" {{ {fields} }}{self.arrow}" if self.fields else self.arrow
        return Variant(self.selector, self.name, rest)

    @property
    def pattern(self):
        return "{ " + ", ".join(f.name for f in self.fields) + " }" if self.fields else "{}"

    @property
    def handler(self):
        """The recv arm, indented to sit inside the contract."""
        uses = f" uses ({self.uses})" if self.uses else ""
        return (f"        {self.name} {self.pattern}{self.arrow}{uses} {{\n"
                + textwrap.indent(self.body, 12 * " ") + "\n        }")


A = (Field("a", "u256"),)
AB = (Field("a", "u256"), Field("b", "u256"))
N = (Field("n", "u256"),)
OPS_ARMS = [
    Arm("Add", AB, "u256", "a + b"),
    Arm("Sub", AB, "u256", "a - b"),
    Arm("Mul", AB, "u256", "a * b"),
    Arm("Div", AB, "u256", "a / b"),
    Arm("Mod", AB, "u256", "a % b"),
    Arm("Shl", AB, "u256", "a << b"),
    Arm("Shr", AB, "u256", "a >> b"),
    Arm("Bits", AB, "u256", "(a & b) | (a ^ b) | ~a"),
    Arm("Cmp", AB, "u256", "flags(a < b, a <= b, a > b, a >= b, a == b, a != b)"),
    Arm("Logic", (Field("a", "bool"), Field("b", "bool")), "bool", "(a && !b) || (!a && b)"),
    Arm("Short", (Field("a", "bool"), Field("b", "u256")), "bool",
        "(a || 1 / b == 0) && (!a || b == 0 || 1 / b == 0 || true)"),
    Arm("Fact", N, "u256", "fact(n)"),
    Arm("Sum", N, "u256", "sum_odd(n)"),
    Arm("Early", A, "u256", "early(a) + early(a)"),
    Arm("Order", A, "u256", "1 / a + (a - 1)"),
    Arm("Args", A, "u256", "pair(p: 1 / a, q: a - 1)"),
    Arm("Assert", A, None, "assert!(a != 0)"),
    Arm("AssertMsg", A, None, 'assert!(a != 0, "a is zero")'),
    Arm("AssertEmpty", A, None, 'assert!(a != 0, "")'),
    Arm("Aug", AB, "u256", "aug(a, b)"),
    Arm("Chain", A, "u256", "if a == 0 { 10 } else if a == 1 { 11 } else if a == 2 { 12 } else { 13 }"),
    Arm("Store", (Field("a", "u256"), Field("b", "bool"), Field("c", "Address")), None, "x = a\nflag = b\nwho = c",
        uses="mut x, mut flag, mut who"),
    Arm("LoadX", (), "u256", "x", uses="x"),
    Arm("LoadFlag", (), "bool", "flag", uses="flag"),
    Arm("LoadWho", (), "Address", "who", uses="who"),
    Arm("Same", (Field("a", "Address"), Field("b", "Address")), "bool", "a == b"),
    Arm("Swap", AB, "u256", "{\n    let t = a\n    x = b\n    return t\n}", uses="mut x"),
    Arm("Bump", (), "u256", "x = bump_x(x)\nx", uses="mut x"),
]
OPS_MSG = Msg("CgOpsMsg", tuple(arm.variant for arm in OPS_ARMS))


def op(name, *words, **kw):
    """A call to the CgOps arm `name`."""
    return OPS_MSG.call(name, *words, **kw)


OPS_FNS = """const TEN: u256 = 10

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
"""



def ops_program():
    arms = "\n".join(arm.handler for arm in OPS_ARMS)
    return (OPS_MSG.source + "\n" + OPS_FNS + "\ncontract CgOps {\n    mut x: u256,\n    mut flag: bool,\n"
            "    mut who: Address,\n\n    recv CgOpsMsg {\n" + arms + "\n    }\n}\n")


def ops_calls():
    c = []
    for a, b in [(2, 3), (MAX, 1), (MAX, 0), (1, MAX), (7, 7)]:
        c += [op("Add", a, b), op("Sub", a, b), op("Sub", b, a), op("Mul", a, b), op("Div", a, b),
              op("Mod", a, b), op("Bits", a, b), op("Cmp", a, b), op("Cmp", b, a), op("Aug", a, b)]
    c += [op("Mul", 0, MAX), op("Mul", 1 << 128, 1 << 128), op("Mul", 1 << 127, 1 << 128),
          op("Div", 7, 0), op("Mod", 7, 0), op("Mod", 7, 3)]
    c += [op("Shl", 3, 255), op("Shl", 1, 256), op("Shr", MAX, 300), op("Shr", MAX, 4)]
    c += [op("Logic", a, b) for a in (0, 1) for b in (0, 1)]
    c += [op("Logic", 2, 0), op("Logic", 0, 2)]
    c += [op("Short", 1, 0), op("Short", 0, 0), op("Short", 0, 1)]
    c += [op("Fact", n) for n in (0, 1, 5, 57, 58)]
    c += [op("Sum", n) for n in (0, 1, 10)]
    c += [op("Early", 0), op("Early", 5), op("Order", 0), op("Args", 0), op("Args", 2)]
    c += [op("Assert", 0), op("Assert", 1), op("AssertMsg", 0), op("AssertMsg", 1), op("AssertEmpty", 0)]
    c += [op("Chain", n) for n in range(4)]
    c += [op("LoadX"), op("Store", 5, 1, 0xcc), op("LoadX"), op("LoadFlag"), op("LoadWho"),
          op("Store", 6, 2, 0xcc), op("Store", 6, 0, (1 << 160) | 0xcc), op("LoadX"),
          op("Swap", 1, 2), op("LoadX"), op("Bump"), op("Bump"), op("LoadX")]
    c += [op("Same", 0xcc, 0xcc), op("Same", 0xcc, 0xdd), op("Same", 1 << 160, 0)]
    # Short calldata, extra bytes and value.
    c += [op("Add", 1), op("Add", 1, 2, extra=3), op("LoadX", value=5), op("LoadX", extra=1)]
    return c


INIT_MSG = Msg("CgInitMsg", (
    Variant(1, "Get", " -> u256"),
    Variant(2, "Flag", " -> bool"),
    Variant(3, "Who", " -> Address"),
))
INIT = INIT_MSG.source + """
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
"""

MISC_MSG = Msg("CgMiscMsg", (
    Variant(1, "Unit", " { a: u256 } -> u256"),
    Variant(2, "Pending", " { a: u256 } -> u256"),
    Variant(3, "Deep", " { n: u256 } -> u256"),
    Variant(4, "Who", " { a: Address, b: Address } -> Address"),
    Variant(5, "Long", " { a: u256 }"),
    Variant(6, "Shadow", " { a: u256 } -> u256"),
    Variant(7, "Flag", " {} -> bool"),
))
MISC = MISC_MSG.source + """
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
"""

NO_RECV = """contract CgNoRecv {
    mut n: u256,
}
"""
# The last branch of CgChain holds the deepest nesting that the parser accepts inside an arm.
# One more level of either kind fails with P_TOO_DEEP.
DEEPEST_PARENS_IN_ARM = 16
DEEPEST_BLOCKS_IN_ARM = 7
CHAIN_MSG = Msg("CgChainMsg", (Variant(1, "Pick", " { a: u256 } -> u256"),))
CHAIN = (CHAIN_MSG.source + "\ncontract CgChain {\n"
         "    recv CgChainMsg {\n        Pick { a } -> u256 {\n            "
         + " else ".join(f"if a == {k} {{ {k} }}" for k in range(CHAIN_LEN))
         + " else { " + "(" * DEEPEST_PARENS_IN_ARM + "a" + ")" * DEEPEST_PARENS_IN_ARM
         + " + " + "{ " * DEEPEST_BLOCKS_IN_ARM + "1" + " }" * DEEPEST_BLOCKS_IN_ARM + " }\n        }\n    }\n}\n")


# The case number of the main deployment. Smaller numbers name the other deployments, in order
# from 1, and larger numbers name the calls. In hex, a failed test's panic code then ends in the
# case: 0x1_0000_1003 is the third call (fegen.Kind).
MAIN_CASE = 0x1000


def program(test, contract, source, calls, deploys=(), main=Deploy()):
    """Returns the differential test of `source` that sends it `calls` and `deploys`, numbered
    around MAIN_CASE."""
    cases = Cases(Case(MAIN_CASE, main), [Case(n, d) for n, d in enumerate(deploys, start=1)],
                  [Case(n, c) for n, c in enumerate(calls, start=MAIN_CASE + 1)])
    return DiffTest(test, contract, source, cases)


PROGRAMS = [
    program("counter", "CgCounter", COUNTER,
            [COUNTER_MSG.call("Get"), COUNTER_MSG.call("Increment"), COUNTER_MSG.call("Increment"),
             COUNTER_MSG.call("Get"), COUNTER_MSG.call("Increment", value=1), COUNTER_MSG.call("Get", 5)],
            deploys=[Deploy(value=5), Deploy(extra=1)]),
    program("ops", "CgOps", ops_program(), ops_calls()),
    program("init", "CgInit", INIT, [INIT_MSG.call("Get"), INIT_MSG.call("Flag"), INIT_MSG.call("Who")],
            deploys=[Deploy(), Deploy(0xaa, 1), Deploy(0xaa, 2, 0xcc), Deploy(0xaa, 1, (1 << 200) | 0xcc),
                     Deploy(0xaa, 1, 0xcc, extra=7), Deploy(0xaa, 1, 0xcc, value=5)],
            main=Deploy(0xaa, 1, 0xcc)),
    program("misc", "CgMisc", MISC,
            [MISC_MSG.call("Unit", a) for a in (0, 1, 6, 7, 9)]
            + [MISC_MSG.call("Pending", a) for a in (0, 5, 150)]
            + [MISC_MSG.call("Deep", 0), MISC_MSG.call("Deep", 300),
               MISC_MSG.call("Who", 0xaa, 0xbb), MISC_MSG.call("Who", 0xaa, 0xaa),
               MISC_MSG.call("Long", 0), MISC_MSG.call("Long", 1), MISC_MSG.call("Shadow", 4), MISC_MSG.call("Flag")]),
    program("chain", "CgChain", CHAIN,
            [CHAIN_MSG.call("Pick", k) for k in (0, 1, CHAIN_LEN // 2, CHAIN_LEN - 1, CHAIN_LEN, CHAIN_LEN + 1)]),
    program("no_recv", "CgNoRecv", NO_RECV, [Call(1)], deploys=[Deploy(5)]),
]


PRELUDE = """// Generated by tools/gen_codegen_tests.py. Edit the programs there and rerun it.
// Differential tests of code generation, which DESIGN.md §10 describes.
// They need the EVM. docs/WORKAROUNDS.md explains the attribute below.
#![cfg(target = "evm")]

use ingot::diag::{Diag, G_NO_CONTRACT, T_MISMATCH}
""" + difftest_use("ingot") + """
use ingot::lexer::Pos
use std::abi::DynString
"""

ERRORS = """
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
"""



def main():
    out = [PRELUDE]
    for p in PROGRAMS:
        out += ["", p.source]
    for p in PROGRAMS:
        out += p.lines()
    out.append(ERRORS)
    write_formatted(FE0 / "src/codegen_tests.fe", "\n".join(out) + "\n")


main()
