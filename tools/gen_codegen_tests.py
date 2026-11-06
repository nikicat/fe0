#!/usr/bin/env python3
"""Generate fe0/src/codegen_tests.fe and format it with fe fmt.

Each program is written once below. The script puts its text into the module twice: as Fe
code for the official compiler, and as a string literal that Fe0 compiles inside the test.

Contract and msg names must be unique across the fe0 ingot (WORKAROUNDS.md), so they start
with `Cg`.

usage: gen_codegen_tests.py [path/to/fe]
"""
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

FE = sys.argv[1] if len(sys.argv) > 1 else Path.home() / ".fe/bin/fe"
FE0 = Path(__file__).resolve().parent.parent / "fe0"
MAX = (1 << 256) - 1


def lit(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


class Payload:
    """Bytes sent to a contract, together with a value in wei."""

    def __init__(self, value):
        self.value = value

    @property
    def wei(self):
        """The Fe expression for the value."""
        return f"std::evm::wei({self.value})" if self.value else "Wei::zero()"

    def build(self, var):
        """Returns the Fe statements that declare `var` and fill it with the bytes."""
        return [f"var {var}: MemVec<u8> = MemVec::new()"] + self.pushes(var)


def push_words(var, words, extra):
    """Returns the Fe statements that append 32-byte `words`, then `extra` bytes of 0x99."""
    return [f"push_be(mut {var}, {w:#x}, bytes: 32)" for w in words] + [f"{var}.push(0x99)"] * extra


class Deploy(Payload):
    """Constructor arguments: words, then `extra` bytes."""

    def __init__(self, *words, extra=0, value=0):
        super().__init__(value)
        self.words, self.extra = words, extra

    def pushes(self, var):
        return push_words(var, self.words, self.extra)


class Call(Payload):
    """Calldata: a 4-byte selector, words, then `extra` bytes."""

    def __init__(self, sel, *words, extra=0, value=0):
        super().__init__(value)
        self.sel, self.words, self.extra = sel, words, extra

    def pushes(self, var):
        return [f"push_be(mut {var}, {self.sel:#x}, bytes: 4)"] + push_words(var, self.words, self.extra)


class RawCall(Payload):
    """Calldata given byte by byte."""

    def __init__(self, *data, value=0):
        super().__init__(value)
        self.data = data

    def pushes(self, var):
        return [f"{var}.push({b})" for b in self.data]


# Calls that reach the dispatcher's empty reverts. Every program gets them after its own calls.
DISPATCH = [RawCall(), RawCall(0, 0, 1), Call(0x7777)]


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
class Arm:
    """One message variant of CgOps and the recv arm that handles it."""

    name: str
    fields: tuple  # (name, type) pairs
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
        fields = ", ".join(f"{n}: {t}" for n, t in self.fields)
        rest = f" {{ {fields} }}{self.arrow}" if self.fields else self.arrow
        return Variant(self.selector, self.name, rest)

    @property
    def pattern(self):
        return "{ " + ", ".join(n for n, _ in self.fields) + " }" if self.fields else "{}"

    @property
    def handler(self):
        """The recv arm, indented to sit inside the contract."""
        uses = f" uses ({self.uses})" if self.uses else ""
        return (f"        {self.name} {self.pattern}{self.arrow}{uses} {{\n"
                + textwrap.indent(self.body, 12 * " ") + "\n        }")


A = (("a", "u256"),)
AB = (("a", "u256"), ("b", "u256"))
N = (("n", "u256"),)
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
    Arm("Logic", (("a", "bool"), ("b", "bool")), "bool", "(a && !b) || (!a && b)"),
    Arm("Short", (("a", "bool"), ("b", "u256")), "bool", "(a || 1 / b == 0) && (!a || b == 0 || 1 / b == 0 || true)"),
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
    Arm("Store", (("a", "u256"), ("b", "bool"), ("c", "Address")), None, "x = a\nflag = b\nwho = c",
        uses="mut x, mut flag, mut who"),
    Arm("LoadX", (), "u256", "x", uses="x"),
    Arm("LoadFlag", (), "bool", "flag", uses="flag"),
    Arm("LoadWho", (), "Address", "who", uses="who"),
    Arm("Same", (("a", "Address"), ("b", "Address")), "bool", "a == b"),
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
# The else-if chain in CgChain is longer than the parser's MAX_DEPTH. The codegen reads such a
# chain in a loop. The last branch holds the deepest nesting the parser accepts inside an arm.
# One more level of either kind fails with P_TOO_DEEP.
CHAIN_LEN = 40
DEEPEST_PARENS_IN_ARM = 16
DEEPEST_BLOCKS_IN_ARM = 7
CHAIN_MSG = Msg("CgChainMsg", (Variant(1, "Pick", " { a: u256 } -> u256"),))
CHAIN = (CHAIN_MSG.source + "\ncontract CgChain {\n"
         "    recv CgChainMsg {\n        Pick { a } -> u256 {\n            "
         + " else ".join(f"if a == {k} {{ {k} }}" for k in range(CHAIN_LEN))
         + " else { " + "(" * DEEPEST_PARENS_IN_ARM + "a" + ")" * DEEPEST_PARENS_IN_ARM
         + " + " + "{ " * DEEPEST_BLOCKS_IN_ARM + "1" + " }" * DEEPEST_BLOCKS_IN_ARM + " }\n        }\n    }\n}\n")


@dataclass(frozen=True)
class Program:
    """One program and what its test sends to it."""

    test: str  # the test function's name
    contract: str
    source: str
    calls: list  # sent to the main deployment, before DISPATCH
    deploys: list = ()  # extra deployments, checked only for whether they create a contract
    main: Deploy = field(default_factory=Deploy)


PROGRAMS = [
    Program("counter", "CgCounter", COUNTER,
            [COUNTER_MSG.call("Get"), COUNTER_MSG.call("Increment"), COUNTER_MSG.call("Increment"),
             COUNTER_MSG.call("Get"), COUNTER_MSG.call("Increment", value=1), COUNTER_MSG.call("Get", 5)],
            deploys=[Deploy(value=5), Deploy(extra=1)]),
    Program("ops", "CgOps", ops_program(), ops_calls()),
    Program("init", "CgInit", INIT, [INIT_MSG.call("Get"), INIT_MSG.call("Flag"), INIT_MSG.call("Who")],
            deploys=[Deploy(), Deploy(0xaa, 1), Deploy(0xaa, 2, 0xcc), Deploy(0xaa, 1, (1 << 200) | 0xcc),
                     Deploy(0xaa, 1, 0xcc, extra=7), Deploy(0xaa, 1, 0xcc, value=5)],
            main=Deploy(0xaa, 1, 0xcc)),
    Program("misc", "CgMisc", MISC,
            [MISC_MSG.call("Unit", a) for a in (0, 1, 6, 7, 9)]
            + [MISC_MSG.call("Pending", a) for a in (0, 5, 150)]
            + [MISC_MSG.call("Deep", 0), MISC_MSG.call("Deep", 300),
               MISC_MSG.call("Who", 0xaa, 0xbb), MISC_MSG.call("Who", 0xaa, 0xaa),
               MISC_MSG.call("Long", 0), MISC_MSG.call("Long", 1), MISC_MSG.call("Shadow", 4), MISC_MSG.call("Flag")]),
    Program("chain", "CgChain", CHAIN,
            [CHAIN_MSG.call("Pick", k) for k in (0, 1, CHAIN_LEN // 2, CHAIN_LEN - 1, CHAIN_LEN, CHAIN_LEN + 1)]),
    Program("no_recv", "CgNoRecv", NO_RECV, [Call(1)], deploys=[Deploy(5)]),
]


PRELUDE = """// Generated by tools/gen_codegen_tests.py. Edit the programs there and rerun it.
// Differential tests for code generation. Fe compiles each program as a contract of this module,
// and Fe0 compiles the same text inside the test. The test deploys both builds the same way and
// sends both the same calls. Each deployment must create a contract from both builds or from
// neither. Each call must give the same success flag and the same return or revert data.

use ingot::codegen::compile
use ingot::diag::{Diag, G_NO_CONTRACT, T_MISMATCH}
use ingot::io::{Source, text}
use std::abi::DynString
use std::evm::{Call, Contract, Create, RawOps}

// Fe0's deploy code for `s`. When Fe0 rejects `s`, fails with Panic(letter << 40 | number << 24
// | pos): the ASCII code of the phase letter, the number within the phase and the byte offset.
fn ours(_ s: DynString) -> MemVec<u8> {
    let out = with (Source = text(s)) {
        compile()
    }
    match out.err {
        Option::Some(d) => {
            let letter = d.code.letter() as u256
            let number = d.code.number() as u256
            core::panic_code(letter << 40 | number << 24 | d.pos as u256)
        },
        Option::None => {},
    }
    out.code
}

// The official deploy code of a contract of this module. It is the `len` bytes at `offset` in
// this test's code.
fn theirs(_ offset: u256, _ len: u256) -> MemVec<u8> uses (evm: mut Evm) {
    var buf = MemBuffer::alloc(len as usize)
    evm.codecopy(dest: mut buf, dest_offset: 0, src_offset: offset, len)
    var v: MemVec<u8> = MemVec::new()
    v.extend_from_slice(buf.span())
    v
}

// Appends the low `bytes` bytes of `x` to `v`, most significant first.
fn push_be(_ v: mut MemVec<u8>, _ x: u256, bytes: u256) {
    var i: u256 = 0
    while i < bytes {
        v.push(((x >> ((bytes - 1 - i) * 8)) & 0xff).downcast_truncate())
        i += 1
    }
}

// The deploy codes of one program from both compilers.
struct Builds { ours: MemVec<u8>, theirs: MemVec<u8> }

impl Builds {
    // Deploys both builds with `args` and `value`. Fails with Panic(`case`) unless both or
    // neither create a contract.
    fn deploy(self, _ args: MemVec<u8>, _ value: Wei, _ case: u256) -> Deployed uses (evm: mut Evm) {
        let p = Deployed { ours: create(self.ours, args, value), theirs: create(self.theirs, args, value) }
        if (p.ours.word() == 0) != (p.theirs.word() == 0) {
            core::panic_code(case)
        }
        p
    }
}

// Deploys `code` followed by `args`.
fn create(_ code: MemVec<u8>, _ args: MemVec<u8>, _ value: Wei) -> Address uses (evm: mut Evm) {
    var v: MemVec<u8> = MemVec::new()
    v.extend_from_slice(code.as_slice())
    v.extend_from_slice(args.as_slice())
    evm.create_raw(value, init_code: v.into_array().span())
}

// One program deployed from both builds.
struct Deployed { ours: Address, theirs: Address }

impl Deployed {
    // Calls both contracts with `data` and `value`. Fails with Panic(`case`) unless the success
    // flags and the return data are the same.
    fn call(self, _ data: own MemVec<u8>, _ value: Wei, _ case: u256) uses (evm: mut Evm) {
        let args = data.into_array()
        let a = evm.try_call_raw(addr: self.ours, gas: 10000000, value, args: args.span())
        let b = evm.try_call_raw(addr: self.theirs, gas: 10000000, value, args: args.span())
        if a.success() != b.success() || a.returndata_len() != b.returndata_len() {
            core::panic_code(case)
        }
        var i: usize = 0
        while i < a.returndata_len() {
            if a.returndata().byte_at(i) != b.returndata().byte_at(i) {
                core::panic_code(case)
            }
            i += 1
        }
    }
}
"""

ERRORS = """
fn fails(_ s: DynString) -> Diag {
    let out = with (Source = text(s)) {
        compile()
    }
    assert!(out.code.len() == 0)
    out.err.unwrap()
}

#[test]
fn errors() {
    let d = fails("fn f() -> u256 { 1 }")
    assert!(d.code == G_NO_CONTRACT)
    // An earlier phase's error is passed on.
    let d = fails("contract C {}\\nfn f() -> u256 { true }")
    assert!(d.code == T_MISMATCH && d.pos == 29)
}
"""



# The case number of the main deployment. Panic codes below it name a side deployment, and
# codes above it name a call.
MAIN_CASE = 1000


def test_fn(p):
    """Returns the lines of the Fe test function for program `p`."""
    out = ["", "#[test(balance = 1000)]", f"fn {p.test}() uses (evm: mut Evm) {{",
           f"    let b = Builds {{ ours: ours({lit(p.source)}), "
           f"theirs: theirs({p.contract}::init_code_offset(), {p.contract}::init_code_len()) }}"]
    for case, d in enumerate(p.deploys, start=1):
        out += block(d.build("a") + [f"let _ = b.deploy(a, {d.wei}, {case})"])
    out += ["    " + s for s in p.main.build("a")]
    out += [f"    let p = b.deploy(a, {p.main.wei}, {MAIN_CASE})", "    assert!(p.ours.word() != 0)"]
    for case, c in enumerate(p.calls + DISPATCH, start=MAIN_CASE + 1):
        out += block(c.build("d") + [f"p.call(d, {c.wei}, {case})"])
    return out + ["}"]


def block(statements):
    """Returns `statements` as a braced block inside a test function."""
    return ["    {"] + ["        " + s for s in statements] + ["    }"]


def main():
    out = [PRELUDE]
    for p in PROGRAMS:
        out += ["", p.source]
    for p in PROGRAMS:
        out += test_fn(p)
    out.append(ERRORS)
    path = FE0 / "src/codegen_tests.fe"
    path.write_text("\n".join(out) + "\n")
    subprocess.run([str(FE), "fmt", str(path)], check=True)


main()
