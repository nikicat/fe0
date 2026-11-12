#!/usr/bin/env python3
"""Generate fe0/src/check_tests.fe and format it with fe fmt.

A case accepts, warns or rejects. A reject or warn case marks the position of its diagnostic
with `|`, and the script turns the mark into a byte offset. Change the cases here and rerun
it, so the offsets stay right.

usage: [FE=path/to/fe] gen_check_tests.py
"""
from dataclasses import dataclass
from enum import Enum
from typing import NewType

from fegen import (CHAIN_LEN, FE0, FeLine, FeName, FeSource, TestName, lines, lit, source,
                   write_formatted)

# A Fe source with one `|`, which marks the byte that a diagnostic points at.
MarkedSource = NewType("MarkedSource", str)


@dataclass(frozen=True)
class Accepts:
    """A case that the checker accepts without warnings."""

    src: FeSource

    def line(self) -> FeLine:
        """The test's line that checks the case."""
        assert "|" not in self.src or "||" in self.src, self.src
        return FeLine(f"    accepts({lit(self.src)})")


class Helper(Enum):
    """The function of check_tests.fe that checks a diagnosed case."""

    WARNS = "warns"
    REJECTS = "rejects"


@dataclass(frozen=True)
class Diagnosed:
    """A case that the checker warns about or rejects, with the constant of fe0/src/diag.fe that
    names the diagnostic's code."""

    helper: Helper
    src: MarkedSource
    code: FeName

    def line(self) -> FeLine:
        """The test's line that checks the case, with the mark turned into a byte offset."""
        i = self.src.index("|")
        unmarked = self.src[:i] + self.src[i + 1:]
        return FeLine(f"    {self.helper.value}({lit(unmarked)}, {self.code}, {i})")


Case = Accepts | Diagnosed


def ok(src: str) -> Accepts:
    """The case of the source `src`, which the checker accepts."""
    return Accepts(FeSource(src))


def warn(src: str, code: str) -> Diagnosed:
    """The case of the marked source `src`, which the checker warns about with the diag code
    `code`."""
    return Diagnosed(Helper.WARNS, MarkedSource(src), FeName(code))


def err(src: str, code: str) -> Diagnosed:
    """The case of the marked source `src`, which the checker rejects with the diag code
    `code`."""
    return Diagnosed(Helper.REJECTS, MarkedSource(src), FeName(code))


# The msg that every contract case receives.
MSG = "msg M {\n    #[selector = 0x01]\n    Get -> u256,\n    #[selector = 0x02]\n    Set { v: u256 },\n}\n"
# The field that GET_OK and ARMS_OK read and write.
FIELD_A = "    mut a: u256\n"
GET_OK = "        Get {} -> u256 uses (a) { a }\n"
ARMS_OK = GET_OK + "        Set { v } uses (mut a) { a = v }\n"
# The fields of the maps cases. FIELD_A stays because GET_OK reads it.
MAPS = FIELD_A + "    mut m: StorageMap<Address, u256>\n    mut f: StorageMap<u256, bool>\n"
# `msgs` go after MSG and `recvs` after `recv M`.
def contract(arms: str, body_fields: str = FIELD_A, init: str = "", msgs: str = "",
             recvs: str = "") -> str:
    return (MSG + msgs + "contract K {\n" + body_fields + init + "    recv M {\n" + arms + "    }\n"
            + recvs + "}\n")
def set_arm(body: str, fields: str = FIELD_A) -> str:
    """The contract with the fields `fields`, GET_OK, and a Set arm whose text after `Set { v } `
    is `body`."""
    return contract(GET_OK + "        Set { v } " + body + "\n", fields)
RECV_N = "    recv N {\n        O {} { }\n    }\n"
groups: dict[TestName, list[Case]] = {
TestName("types_of_operators"): [
    ok("fn f(_ a: u256, _ b: bool, _ c: Address, _ d: Address) -> bool {\n    a + 1 * 2 / 3 % 4 & 5 | 6 ^ 7 << 8 >> 9 > 0 && !b || c == d && ~a != 0\n}"),
    ok("fn f(_ a: u256) -> bool { a < 1 || a <= 1 || a > 1 || a >= 1 }"),
    err("fn f(_ b: bool) -> u256 { |b + 1 }", "T_MISMATCH"),
    err("fn f(_ a: u256) -> bool { |a && true }", "T_MISMATCH"),
    err("fn f(_ a: Address, _ b: Address) -> bool { |a < b }", "T_MISMATCH"),
    err("fn f(_ a: u256) -> bool { a == |true }", "T_MISMATCH"),
    err("fn f(_ a: u256) -> bool { !|a }", "T_MISMATCH"),
    err("fn f(_ b: bool) -> bool { ~|b }", "T_MISMATCH"),
    err("fn g() {}\nfn f() -> bool { |g() == g() }", "T_NO_VALUE"),
],
TestName("if_and_blocks"): [
    ok("fn f(_ c: bool) -> u256 { if c { 1 } else if !c { 2 } else { 3 } }"),
    ok("fn f(_ c: bool) { if c { f(c) } }"),
    ok("fn f(_ c: bool) -> u256 {\n    let x = {\n        let y: u256 = 2\n        y * 2\n    }\n    x\n}"),
    err("fn f(_ c: bool) -> u256 { if c |{ 1 } }", "T_MISMATCH"),
    err("fn f(_ c: bool) -> u256 { if c { 1 } else if c { 2 } else |{ true } }", "T_MISMATCH"),
    err("fn f(_ c: bool) -> u256 { if c { 1 } else if c |{ 2 } }", "T_MISMATCH"),
    err("fn f() -> u256 { if |1 { 1 } else { 2 } }", "T_MISMATCH"),
    err("fn f() { assert!(|1) }", "T_MISMATCH"),
    ok("fn f(_ a: u256) { assert!(a > 0, \"zero\") }"),
],
TestName("return_paths"): [
    ok("fn f() -> u256 { return 1 }"),
    ok("fn f(_ c: bool) -> u256 { if c { return 1 } else { return 2 } }"),
    ok("fn f(_ c: bool) -> u256 {\n    if c { return 1 }\n    2\n}"),
    ok("fn f() { return }"),
    err("fn f(_ c: bool) -> u256 |{ if c { return 1 } }", "T_MISMATCH"),
    err("fn f() -> u256 |{ while true { return 1 } }", "T_MISMATCH"),
    err("fn f() { return |1 }", "T_MISMATCH"),
    err("fn f() -> u256 { |return }", "T_MISMATCH"),
    # A tail after a diverging statement still gives the block its type (SPEC §5).
    ok("fn f() -> u256 {\n    return 1\n    2\n}"),
    err("fn f() -> u256 |{\n    return 1\n    true\n}", "T_MISMATCH"),
    err("fn f() {\n    while true |{\n        break\n        5\n    }\n}", "T_MISMATCH"),
    err("fn f() |{ 1 }", "T_MISMATCH"),
],
TestName("locals"): [
    ok("fn f() -> u256 {\n    let x: u256 = 1\n    let x = x + 1\n    x\n}"),
    ok("fn f() -> u256 {\n    var x: u256 = 1\n    x += 2\n    x = x * 3\n    x\n}"),
    err("fn f() -> u256 {\n    { let x: u256 = 1 }\n    |x\n}", "N_UNKNOWN_NAME"),
    err("fn f() -> u256 {\n    let x = |x\n    x\n}", "N_UNKNOWN_NAME"),
    err("fn f() { let x: bool = |1 }", "T_MISMATCH"),
    err("fn g() {}\nfn f() { let x = |g() }", "T_NO_VALUE"),
    err("fn f() {\n    let x: u256 = 1\n    |x = 2\n}", "N_ASSIGN_IMMUTABLE"),
    err("fn f(_ p: u256) { |p = 2 }", "N_ASSIGN_IMMUTABLE"),
    err("const A: u256 = 1\nfn f() { |A = 2 }", "N_ASSIGN_IMMUTABLE"),
    err("fn f() {\n    var b = true\n    |b += true\n}", "T_MISMATCH"),
    err("fn f() {\n    var x: u256 = 1\n    x = |true\n}", "T_MISMATCH"),
    err("fn f() { |y = 1 }", "N_UNKNOWN_NAME"),
    ok("const A: u256 = 1\nfn F() -> u256 { A }"),
    err("fn f() -> u256 {\n    |let Some: u256 = 1\n    Some\n}", "N_UPPERCASE_LOCAL"),
    err("fn f(|_ X: u256) -> u256 { X }", "N_UPPERCASE_LOCAL"),
    err(contract(GET_OK + "        Set { |v: V } { }\n"), "N_UPPERCASE_LOCAL"),
    err("const n: u256 = 5\n" + contract(GET_OK + "        Set { |v: n } { }\n"), "N_SHADOWS_ITEM"),
    err("const n: u256 = 5\nfn f() -> u256 {\n    |let n: u256 = 2\n    n\n}", "N_SHADOWS_ITEM"),
    err("fn g() -> u256 { 1 }\nfn f(|_ g: u256) -> u256 { g }", "N_SHADOWS_ITEM"),
    err("msg m {\n    #[selector = 0x01]\n    A {},\n}\nfn f(|_ m: u256) -> u256 { m }", "N_SHADOWS_ITEM"),
    err("contract k {\n}\nfn f(|_ k: u256) -> u256 { k }", "N_SHADOWS_ITEM"),
],
TestName("literal_types"): [
    # Integers of type TY_INT (SPEC §2). Fe rejects each err case here with 8-0031 too, except
    # `var i = 0`, whose type Fe infers from the later use of `i`.
    ok("fn f() -> u256 {\n    let x: u256 = 1 + 2\n    x << 3\n}"),
    ok("fn f(_ a: u256) -> bool { 1 < a && a == 2 && ~0 != a }"),
    ok("fn f(_ c: bool) -> u256 { if c { 1 } else { 2 } * 3 }"),
    ok("fn g(_ a: u256) {}\nfn f() { g(1 + 1) }"),
    ok("const A: u256 = 1\nfn f() -> bool { A == 1 }"),
    err("fn f() {\n    let x = |1\n}", "T_NEEDS_TYPE"),
    err("fn f() -> u256 {\n    var i = |0\n    i\n}", "T_NEEDS_TYPE"),
    err("fn f() {\n    1 |+ 2\n    f()\n}", "T_NEEDS_TYPE"),
    err("fn f(_ c: bool) {\n    |if c { 1 } else { 2 }\n    f(c)\n}", "T_NEEDS_TYPE"),
    # As a body\'s tail, a literal integer is a value where none may be.
    err("fn f() |{ 1 + 2 }", "T_MISMATCH"),
    err("fn f() -> bool { 1 |== 1 }", "T_NEEDS_TYPE"),
    err("fn f() { assert!(~1 |< 2) }", "T_NEEDS_TYPE"),
    err("const B: bool = 1 |== 1", "T_NEEDS_TYPE"),
    err("const C: bool = 1 |< 2", "T_NEEDS_TYPE"),
],
TestName("loops"): [
    ok("fn f() -> u256 {\n    var i: u256 = 0\n    while i < 10 {\n        i += 1\n        if i == 5 { break }\n        continue\n    }\n    i\n}"),
    err("fn f() { |break }", "N_OUTSIDE_LOOP"),
    err("fn f() { |continue }", "N_OUTSIDE_LOOP"),
    err("fn f() { while |1 { } }", "T_MISMATCH"),
    err("fn f() { while true |{ 1 } }", "T_MISMATCH"),
],
TestName("items_and_names"): [
    ok("fn g() -> u256 { h() }\nfn h() -> u256 { 1 }"),
    err("fn f() {}\n|const f: u256 = 1", "N_DUPLICATE"),
    err("fn f(_ a: u256, |_ a: u256) {}", "N_DUPLICATE"),
    err("fn f() -> u256 { |nope }", "N_UNKNOWN_NAME"),
    err("fn g() {}\nfn f() { let x = |g }", "N_NOT_A_VALUE"),
    err("const A: u256 = 1\nfn f() { |A() }", "N_NOT_A_FUNCTION"),
    err("fn f() { |g() }", "N_UNKNOWN_NAME"),
    err("contract A {}\n|contract B {}", "N_TWO_CONTRACTS"),
],
TestName("calls"): [
    ok("fn g(_ a: u256, b: bool) -> u256 { a }\nfn f(b: bool) -> u256 { g(1, b: b) + g(2, b) }"),
    err("fn g(_ a: u256) {}\nfn f() { |g(1, 2) }", "T_ARG_COUNT"),
    err("fn g(_ a: u256) {}\nfn f() { g(|true) }", "T_MISMATCH"),
    err("fn g(_ a: u256) {}\nfn f() { g(|a: 1) }", "N_BAD_LABEL"),
    err("fn g(a: u256) {}\nfn f() { g(|1) }", "N_BAD_LABEL"),
    err("fn g(a: u256, b: u256) {}\nfn f() { g(|b: 1, a: 2) }", "N_BAD_LABEL"),
    ok("fn g() {}\nfn f() { g() }"),
],
TestName("constants"): [
    ok("const A: u256 = 2 + 3\nconst B: u256 = A * 4 - 1 / 1 % 7\nconst C: bool = B == 19 && !false\nconst D: u256 = 1 << 256"),
    err("const A: u256 = |B\nconst B: u256 = 1", "N_FORWARD_CONST"),
    err("const A: u256 = |A", "N_FORWARD_CONST"),
    err("const A: u256 = 0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff |+ 1", "C_OVERFLOW"),
    err("const A: u256 = 0 |- 1", "C_OVERFLOW"),
    err("const A: u256 = 0x8000000000000000000000000000000000000000000000000000000000000000 |* 2", "C_OVERFLOW"),
    err("const A: u256 = 1 |/ 0", "C_DIV_ZERO"),
    err("const A: u256 = 1 |% 0", "C_DIV_ZERO"),
    err("fn g() -> u256 { 1 }\nconst A: u256 = |g()", "C_NOT_CONST"),
    err("const A: bool = |1", "T_MISMATCH"),
    err("const A: u256 = 1 + |true", "T_MISMATCH"),
],
TestName("effects"): [
    ok(contract(ARMS_OK, init="    init(x: u256) uses (mut a) { a = x }\n")),
    err(contract("        Get {} -> u256 { |a }\n        Set { v } uses (mut a) { a = v }\n"), "E_NOT_IN_USES"),
    err(set_arm("uses (a) { |a = v }"), "E_NOT_MUT"),
    err(set_arm("uses (a) { |a += v }"), "E_NOT_MUT"),
    err(contract("        Get {} -> u256 uses (|b) { 1 }\n        Set { v } { }\n"), "E_UNKNOWN_FIELD"),
    err(contract("        Get {} -> u256 uses (a, |mut a) { a }\n        Set { v } { }\n"), "E_DUPLICATE_USE"),
    err(contract(ARMS_OK) + "fn f() -> u256 { |a }", "E_NOT_IN_USES"),
    warn(contract("        Get {} -> u256 uses (a, |b) { a }\n        Set { v } uses (mut a) { a = v }\n", FIELD_A + "    mut b: u256\n"), "E_UNUSED_USE"),
    warn(contract(ARMS_OK, init="    init() uses (|mut a) { }\n"), "E_UNUSED_USE"),
    ok(contract("        Get {} -> u256 uses (mut a) { a }\n        Set { v } uses (mut a) { a = v }\n")),
    err(contract(ARMS_OK, init="    init(|a: u256) { }\n"), "N_SHADOWS_FIELD"),
    err(contract("        Get {} -> u256 {\n            |let a: u256 = 1\n            a\n        }\n        Set { v } { }\n"), "N_SHADOWS_FIELD"),
    err(contract(ARMS_OK, FIELD_A + "    mut |a: bool\n"), "N_DUPLICATE"),
    err("const a: u256 = 1\n" + contract(ARMS_OK, "    mut |a: u256\n"), "N_DUPLICATE"),
],
TestName("maps"): [
    ok(set_arm("uses (mut m, mut f) {\n            m[Address::zero()] += v\n            f[v] = !f[m[Address::zero()] + 1]\n        }", MAPS)),
    err(set_arm("{ assert!(|m[Address::zero()] == v) }", MAPS), "E_NOT_IN_USES"),
    err(set_arm("uses (m) { |m[Address::zero()] = v }", MAPS), "E_NOT_MUT"),
    err(set_arm("uses (m) { let x = |m }", MAPS), "N_NOT_A_VALUE"),
    err(set_arm("uses (mut m) { |m = v }", MAPS), "N_ASSIGN_IMMUTABLE"),
    err(contract("        Get {} -> u256 uses (a) { |a[1] }\n        Set { v } { }\n", MAPS), "T_MISMATCH"),
    err(set_arm("uses (mut a) { |a[v] = v }", MAPS), "T_MISMATCH"),
    err(set_arm("uses (mut m) { m[|v] = v }", MAPS), "T_MISMATCH"),
    err(set_arm("uses (mut f) { f[v] = |v }", MAPS), "T_MISMATCH"),
    err(set_arm("uses (mut f) { |f[v] += true }", MAPS), "T_MISMATCH"),
    err(set_arm("{ |g[v] = v }", MAPS), "N_UNKNOWN_NAME"),
],
TestName("selectors"): [
    ok("msg N {\n    #[selector = 0xffffffff]\n    A {},\n    #[selector = 0]\n    B {},\n}"),
    err("msg N {\n    |#[selector = 0x100000000]\n    A {},\n}", "T_SELECTOR_TOO_LARGE"),
    err("msg N {\n    #[selector = 1]\n    A {},\n    |#[selector = 0x01]\n    B {},\n}", "N_DUPLICATE_SELECTOR"),
    ok(contract(ARMS_OK, msgs="msg N {\n    #[selector = 0x03]\n    O {},\n}\n", recvs=RECV_N)),
    err(contract(ARMS_OK, msgs="msg N {\n    |#[selector = 0x02]\n    O {},\n}\n", recvs=RECV_N), "N_DUPLICATE_SELECTOR"),
],
TestName("messages"): [
    ok(contract("        Set { v: w } uses (mut a) { a = w }\n" + GET_OK)),
    err(contract(GET_OK) .replace("    recv M", "    |recv M"), "N_MISSING_ARM"),
    err(contract(ARMS_OK + "        |Get {} -> u256 { 1 }\n"), "N_DUPLICATE"),
    err(contract(ARMS_OK + "        |Put {} { }\n"), "N_UNKNOWN_VARIANT"),
    err(contract("        |Get {} uses (a) { }\n        Set { v } uses (mut a) { a = v }\n"), "T_MISMATCH"),
    err(contract(GET_OK + "        Set { |w } { }\n"), "N_UNKNOWN_FIELD"),
    err(contract(GET_OK + "        |Set {} { }\n"), "N_MISSING_BIND"),
    err(contract(GET_OK + "        Set { |v: a } { }\n"), "N_SHADOWS_FIELD"),
    err("fn N() {}\n" + contract("", "").replace("recv M", "|recv N"), "N_NOT_A_MSG"),
    err(contract(ARMS_OK, recvs="    |recv M {\n" + ARMS_OK + "    }\n"), "N_DUPLICATE"),
    err(set_arm("|{ true }"), "T_MISMATCH"),
],
}
codes = sorted({c.code for g in groups.values() for c in g if isinstance(c, Diagnosed)}
               | {FeName("E_TOO_MANY_FIELDS")})
code_uses = "\n".join(f"    {c}," for c in codes)
out = lines(FeSource(f"""// Generated by tools/gen_check_tests.py. Edit the cases there and rerun it.
// Tests for the checker: cases per rule of SPEC §2 and §4–6, each of which accepts, warns or
// rejects. A warn or reject case names the diagnostic's code and the byte offset it points at.

use ingot::ast::{{TY_BOOL, TY_U256}}
use ingot::check::{{Checked, MAX_FIELDS, check}}
use ingot::diag::{{
{code_uses}
    Diag,
    DiagCode,
}}
use ingot::io::{{Source, text}}
use ingot::lexer::Pos
use ingot::parser::{{MAX_DEPTH, parse}}
use ingot::parser_tests::{{Body, DEEPEST_BLOCKS, DEEPEST_PARENS, Framed, Nested, framed}}
use std::abi::DynString

fn checked(_ s: own DynString) -> Checked {{
    with (Source = text(s)) {{
        check(parse())
    }}
}}

// Asserts that the checker accepts `s` without warnings.
fn accepts(_ s: own DynString) {{
    let c = checked(s)
    assert!(c.err.is_none())
    assert!(c.warns.len() == 0)
}}

// Asserts that the checker accepts `s` with one warning, of `code` at byte `pos`.
fn warns(_ s: own DynString, _ code: DiagCode, _ pos: usize) {{
    let c = checked(s)
    assert!(c.err.is_none())
    assert!(c.warns.len() == 1)
    assert!(c.warns[0].code == code)
    assert!(c.warns[0].pos() == Pos::at(pos))
}}

fn rejects(_ s: own DynString, _ code: DiagCode, _ pos: usize) {{
    let d = checked(s).err.unwrap()
    assert!(d.code == code)
    assert!(d.pos() == Pos::at(pos))
}}"""))
for name, cases in groups.items():
    out += [FeLine(""), FeLine("#[test]"), FeLine(f"fn {name}() {{")] + [c.line() for c in cases]
    out.append(FeLine("}"))
SIDE = ("const A: u256 = 6 * 7\nfn f(_ p: u256) -> u256 {\n    let x = p + A\n    var y = x\n    y\n}\n"
        + set_arm("uses (mut b) { b = v == A }", FIELD_A + "    mut b: bool\n"))
PLACES = contract("        Get {} -> u256 uses (d) { d }\n        Set { v } uses (mut d) { d = v }\n",
                  "    mut a: Address\n    mut b: bool\n    mut c: Address\n    mut d: u256\n"
                  "    mut e: bool\n")
CHAIN = "fn f(_ c: bool) -> u256 { " + " else ".join(f"if c {{ {k} }}" for k in range(CHAIN_LEN)) + " else { 0 } }"
out += lines(FeSource(f"""
// The side tables that code generation reads.
#[test]
fn side_tables() {{
    let c = checked({lit(SIDE)})
    assert!(c.err.is_none())
    let items = c.ast.items
    let a = c.ast.list_at(items, 0)
    assert!(c.const_value(a) == 42)
    // f has three frame slots: p, x and y.
    let f = c.ast.list_at(items, 1)
    assert!(c.frame_slots(f) == 3)
    let k = c.ast.list_at(items, 3)
    let fields = c.ast.node(k).list()
    let b = c.ast.list_at(fields, 1)
    assert!(c.storage_place(b).slot() == 1)
    assert!(c.storage_place(b).whole())
    assert!(c.ty(b) == TY_BOOL)
    // In `Get`, the tail `a` resolves to field a.
    let recv = c.ast.list_at(c.ast.node(k).recvs(), 0)
    let get = c.ast.list_at(c.ast.node(recv).list(), 0)
    let tail = c.ast.node(c.ast.node(get).body()).value()
    assert!(c.resolved(tail) == c.ast.list_at(fields, 0))
    assert!(c.ty(tail) == TY_U256)
    assert!(c.resolved(get) == c.ast.list_at(c.ast.node(c.resolved(recv)).list(), 0))
}}

// Fields narrower than a slot share one, in declaration order from the low end (SPEC §6).
#[test]
fn storage_places() {{
    let c = checked({lit(PLACES)})
    assert!(c.err.is_none())
    let fields = c.ast.node(c.the_contract).list()
    let a = c.storage_place(c.ast.list_at(fields, 0))
    assert!(a.slot() == 0 && a.shift() == 0 && a.shared_above() && !a.whole())
    let b = c.storage_place(c.ast.list_at(fields, 1))
    assert!(b.slot() == 0 && b.shift() == 160 && !b.shared_above() && b.mask() == 0xff)
    // c's 20 bytes do not fit in the 11 left in slot 0.
    let c2 = c.storage_place(c.ast.list_at(fields, 2))
    assert!(c2.slot() == 1 && c2.whole())
    let d = c.storage_place(c.ast.list_at(fields, 3))
    assert!(d.slot() == 2 && d.whole())
    // A field after a u256 starts a new slot.
    let e = c.storage_place(c.ast.list_at(fields, 4))
    assert!(e.slot() == 3 && e.whole())
}}

fn nested(_ brackets: String<2>, _ depth: usize) -> Option<Diag> {{
    with (Source = Nested {{ brackets, depth }}.source()) {{
        check(parse()).err
    }}
}}

// Checks the recursion bound of DESIGN.md §5 at the deepest nesting the parser accepts.
#[test]
fn deep_nesting_and_long_chains() {{
    assert!(nested("()", DEEPEST_PARENS).is_none())
    assert!(nested("{{}}", DEEPEST_BLOCKS).is_none())
    assert!({CHAIN_LEN} > MAX_DEPTH)
    accepts({lit(CHAIN)})
}}
"""))
# A contract with more fields than the checker allows, generated by a Source so that the file
# holds no 257-line literal.
out += lines(FeSource(r'''
// A line that declares a field.
const FIELD_LINE: String<19> = "    mut f000: u256\n"

// Where the field's name starts in FIELD_LINE. The name is `f` and then the field's number in
// three digits.
const FIELD_NAME_AT: usize = 8

// The line that opens the contract, before the field lines.
const FIELDS_HEAD: String<31> = "contract K {\n"

// The lines that declare `count` fields named f000, f001 and so on.
struct Fields { count: usize }

impl Fields {
    // A `Source` of a contract with these fields.
    fn source(own self) -> Framed<Fields> {
        framed(FIELDS_HEAD, self, "}\n")
    }
}

impl Body for Fields {
    fn len(self) -> usize {
        self.count * FIELD_LINE.len()
    }

    fn at(self, _ i: usize) -> u8 {
        let digits: String<10> = "0123456789"
        let field = i / FIELD_LINE.len()
        let j = i % FIELD_LINE.len()
        if j > FIELD_NAME_AT && j <= FIELD_NAME_AT + 3 {
            let place: usize = if j == FIELD_NAME_AT + 1 {
                100
            } else if j == FIELD_NAME_AT + 2 { 10 } else { 1 }
            return digits.byte_at(field / place % 10)
        }
        FIELD_LINE.byte_at(j)
    }
}

fn fields(_ count: usize) -> Option<Diag> {
    with (Source = Fields { count }.source()) {
        check(parse()).err
    }
}

#[test]
fn too_many_fields() {
    assert!(fields(MAX_FIELDS).is_none())
    let d = fields(MAX_FIELDS + 1).unwrap()
    assert!(d.code == E_TOO_MANY_FIELDS)
    // The error points at the name of the extra field.
    assert!(d.pos() == Pos::at(FIELDS_HEAD.len() + MAX_FIELDS * FIELD_LINE.len() + FIELD_NAME_AT))
}
'''.rstrip("\n")))
write_formatted(FE0 / "src/check_tests.fe", source(out))
