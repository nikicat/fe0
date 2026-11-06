#!/usr/bin/env python3
"""Generate fe0/src/check_tests.fe and format it with fe fmt.

A case accepts, warns or rejects. A reject or warn case marks the position of its diagnostic
with `|`, and the script turns the mark into a byte offset. Change the cases here and rerun
it, so the offsets stay right.

usage: [FE=path/to/fe] gen_check_tests.py
"""
from fegen import CHAIN_LEN, FE0, lit, write_formatted

# The msg that every contract case receives.
MSG = "msg M {\n    #[selector = 0x01]\n    Get -> u256,\n    #[selector = 0x02]\n    Set { v: u256 },\n}\n"
# `msgs` go after MSG and `recvs` after `recv M`.
def contract(body_fields, arms, init="", msgs="", recvs=""):
    return (MSG + msgs + "contract K {\n" + body_fields + init + "    recv M {\n" + arms + "    }\n"
            + recvs + "}\n")
RECV_N = "    recv N {\n        O {} { }\n    }\n"
GET_OK = "        Get {} -> u256 uses (a) { a }\n"
ARMS_OK = GET_OK + "        Set { v } uses (mut a) { a = v }\n"
groups = {
"types_of_operators": [
    ("ok", "fn f(_ a: u256, _ b: bool, _ c: Address, _ d: Address) -> bool {\n    a + 1 * 2 / 3 % 4 & 5 | 6 ^ 7 << 8 >> 9 > 0 && !b || c == d && ~a != 0\n}"),
    ("ok", "fn f(_ a: u256) -> bool { a < 1 || a <= 1 || a > 1 || a >= 1 }"),
    ("err", "fn f(_ b: bool) -> u256 { |b + 1 }", "T_MISMATCH"),
    ("err", "fn f(_ a: u256) -> bool { |a && true }", "T_MISMATCH"),
    ("err", "fn f(_ a: Address, _ b: Address) -> bool { |a < b }", "T_MISMATCH"),
    ("err", "fn f(_ a: u256) -> bool { a == |true }", "T_MISMATCH"),
    ("err", "fn f(_ a: u256) -> bool { !|a }", "T_MISMATCH"),
    ("err", "fn f(_ b: bool) -> bool { ~|b }", "T_MISMATCH"),
    ("err", "fn g() {}\nfn f() -> bool { |g() == g() }", "T_NO_VALUE"),
],
"if_and_blocks": [
    ("ok", "fn f(_ c: bool) -> u256 { if c { 1 } else if !c { 2 } else { 3 } }"),
    ("ok", "fn f(_ c: bool) { if c { f(c) } }"),
    ("ok", "fn f(_ c: bool) -> u256 {\n    let x = {\n        let y: u256 = 2\n        y * 2\n    }\n    x\n}"),
    ("err", "fn f(_ c: bool) -> u256 { if c |{ 1 } }", "T_MISMATCH"),
    ("err", "fn f(_ c: bool) -> u256 { if c { 1 } else if c { 2 } else |{ true } }", "T_MISMATCH"),
    ("err", "fn f(_ c: bool) -> u256 { if c { 1 } else if c |{ 2 } }", "T_MISMATCH"),
    ("err", "fn f() -> u256 { if |1 { 1 } else { 2 } }", "T_MISMATCH"),
    ("err", "fn f() { assert!(|1) }", "T_MISMATCH"),
    ("ok", "fn f(_ a: u256) { assert!(a > 0, \"zero\") }"),
],
"return_paths": [
    ("ok", "fn f() -> u256 { return 1 }"),
    ("ok", "fn f(_ c: bool) -> u256 { if c { return 1 } else { return 2 } }"),
    ("ok", "fn f(_ c: bool) -> u256 {\n    if c { return 1 }\n    2\n}"),
    ("ok", "fn f() { return }"),
    ("err", "fn f(_ c: bool) -> u256 |{ if c { return 1 } }", "T_MISMATCH"),
    ("err", "fn f() -> u256 |{ while true { return 1 } }", "T_MISMATCH"),
    ("err", "fn f() { return |1 }", "T_MISMATCH"),
    ("err", "fn f() -> u256 { |return }", "T_MISMATCH"),
    ("err", "fn f() |{ 1 }", "T_MISMATCH"),
],
"locals": [
    ("ok", "fn f() -> u256 {\n    let x: u256 = 1\n    let x = x + 1\n    x\n}"),
    ("ok", "fn f() -> u256 {\n    var x: u256 = 1\n    x += 2\n    x = x * 3\n    x\n}"),
    ("err", "fn f() -> u256 {\n    { let x: u256 = 1 }\n    |x\n}", "N_UNKNOWN_NAME"),
    ("err", "fn f() -> u256 {\n    let x = |x\n    x\n}", "N_UNKNOWN_NAME"),
    ("err", "fn f() { let x: bool = |1 }", "T_MISMATCH"),
    ("err", "fn g() {}\nfn f() { let x = |g() }", "T_NO_VALUE"),
    ("err", "fn f() {\n    let x: u256 = 1\n    |x = 2\n}", "N_ASSIGN_IMMUTABLE"),
    ("err", "fn f(_ p: u256) { |p = 2 }", "N_ASSIGN_IMMUTABLE"),
    ("err", "const A: u256 = 1\nfn f() { |A = 2 }", "N_ASSIGN_IMMUTABLE"),
    ("err", "fn f() {\n    var b = true\n    |b += true\n}", "T_MISMATCH"),
    ("err", "fn f() {\n    var x: u256 = 1\n    x = |true\n}", "T_MISMATCH"),
    ("err", "fn f() { |y = 1 }", "N_UNKNOWN_NAME"),
    ("ok", "const A: u256 = 1\nfn F() -> u256 { A }"),
    ("err", "fn f() -> u256 {\n    |let Some: u256 = 1\n    Some\n}", "N_UPPERCASE_LOCAL"),
    ("err", "fn f(|_ X: u256) -> u256 { X }", "N_UPPERCASE_LOCAL"),
    ("err", contract("    mut a: u256\n", GET_OK + "        Set { |v: V } { }\n"), "N_UPPERCASE_LOCAL"),
],
"literal_types": [
    # Integers of type TY_INT (SPEC §2). Fe rejects each err case here with 8-0031 too, except
    # `var i = 0`, whose type Fe infers from the later use of `i`.
    ("ok", "fn f() -> u256 {\n    let x: u256 = 1 + 2\n    x << 3\n}"),
    ("ok", "fn f(_ a: u256) -> bool { 1 < a && a == 2 && ~0 != a }"),
    ("ok", "fn f(_ c: bool) -> u256 { if c { 1 } else { 2 } * 3 }"),
    ("ok", "fn g(_ a: u256) {}\nfn f() { g(1 + 1) }"),
    ("ok", "const A: u256 = 1\nfn f() -> bool { A == 1 }"),
    ("err", "fn f() {\n    let x = |1\n}", "T_NEEDS_TYPE"),
    ("err", "fn f() -> u256 {\n    var i = |0\n    i\n}", "T_NEEDS_TYPE"),
    ("err", "fn f() {\n    1 |+ 2\n    f()\n}", "T_NEEDS_TYPE"),
    ("err", "fn f(_ c: bool) {\n    |if c { 1 } else { 2 }\n    f(c)\n}", "T_NEEDS_TYPE"),
    # As a body\'s tail, a literal integer is a value where none may be.
    ("err", "fn f() |{ 1 + 2 }", "T_MISMATCH"),
    ("err", "fn f() -> bool { 1 |== 1 }", "T_NEEDS_TYPE"),
    ("err", "fn f() { assert!(~1 |< 2) }", "T_NEEDS_TYPE"),
    ("err", "const B: bool = 1 |== 1", "T_NEEDS_TYPE"),
    ("err", "const C: bool = 1 |< 2", "T_NEEDS_TYPE"),
],
"loops": [
    ("ok", "fn f() -> u256 {\n    var i: u256 = 0\n    while i < 10 {\n        i += 1\n        if i == 5 { break }\n        continue\n    }\n    i\n}"),
    ("err", "fn f() { |break }", "N_OUTSIDE_LOOP"),
    ("err", "fn f() { |continue }", "N_OUTSIDE_LOOP"),
    ("err", "fn f() { while |1 { } }", "T_MISMATCH"),
    ("err", "fn f() { while true |{ 1 } }", "T_MISMATCH"),
],
"items_and_names": [
    ("ok", "fn g() -> u256 { h() }\nfn h() -> u256 { 1 }"),
    ("err", "fn f() {}\n|const f: u256 = 1", "N_DUPLICATE"),
    ("err", "fn f(_ a: u256, |_ a: u256) {}", "N_DUPLICATE"),
    ("err", "fn f() -> u256 { |nope }", "N_UNKNOWN_NAME"),
    ("err", "fn g() {}\nfn f() { let x = |g }", "N_NOT_A_VALUE"),
    ("err", "const A: u256 = 1\nfn f() { |A() }", "N_NOT_A_FUNCTION"),
    ("err", "fn f() { |g() }", "N_UNKNOWN_NAME"),
    ("err", "contract A {}\n|contract B {}", "N_TWO_CONTRACTS"),
],
"calls": [
    ("ok", "fn g(_ a: u256, b: bool) -> u256 { a }\nfn f(b: bool) -> u256 { g(1, b: b) + g(2, b) }"),
    ("err", "fn g(_ a: u256) {}\nfn f() { |g(1, 2) }", "T_ARG_COUNT"),
    ("err", "fn g(_ a: u256) {}\nfn f() { g(|true) }", "T_MISMATCH"),
    ("err", "fn g(_ a: u256) {}\nfn f() { g(|a: 1) }", "N_BAD_LABEL"),
    ("err", "fn g(a: u256) {}\nfn f() { g(|1) }", "N_BAD_LABEL"),
    ("err", "fn g(a: u256, b: u256) {}\nfn f() { g(|b: 1, a: 2) }", "N_BAD_LABEL"),
    ("ok", "fn g() {}\nfn f() { g() }"),
],
"constants": [
    ("ok", "const A: u256 = 2 + 3\nconst B: u256 = A * 4 - 1 / 1 % 7\nconst C: bool = B == 19 && !false\nconst D: u256 = 1 << 256"),
    ("err", "const A: u256 = |B\nconst B: u256 = 1", "N_FORWARD_CONST"),
    ("err", "const A: u256 = |A", "N_FORWARD_CONST"),
    ("err", "const A: u256 = 0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff |+ 1", "C_OVERFLOW"),
    ("err", "const A: u256 = 0 |- 1", "C_OVERFLOW"),
    ("err", "const A: u256 = 0x8000000000000000000000000000000000000000000000000000000000000000 |* 2", "C_OVERFLOW"),
    ("err", "const A: u256 = 1 |/ 0", "C_DIV_ZERO"),
    ("err", "const A: u256 = 1 |% 0", "C_DIV_ZERO"),
    ("err", "fn g() -> u256 { 1 }\nconst A: u256 = |g()", "C_NOT_CONST"),
    ("err", "const A: bool = |1", "T_MISMATCH"),
    ("err", "const A: u256 = 1 + |true", "T_MISMATCH"),
],
"effects": [
    ("ok", contract("    mut a: u256\n", ARMS_OK, "    init(x: u256) uses (mut a) { a = x }\n")),
    ("err", contract("    mut a: u256\n", "        Get {} -> u256 { |a }\n        Set { v } uses (mut a) { a = v }\n"), "E_NOT_IN_USES"),
    ("err", contract("    mut a: u256\n", GET_OK + "        Set { v } uses (a) { |a = v }\n"), "E_NOT_MUT"),
    ("err", contract("    mut a: u256\n", GET_OK + "        Set { v } uses (a) { |a += v }\n"), "E_NOT_MUT"),
    ("err", contract("    mut a: u256\n", "        Get {} -> u256 uses (|b) { 1 }\n        Set { v } { }\n"), "E_UNKNOWN_FIELD"),
    ("err", contract("    mut a: u256\n", "        Get {} -> u256 uses (a, |mut a) { a }\n        Set { v } { }\n"), "E_DUPLICATE_USE"),
    ("err", contract("    mut a: u256\n", ARMS_OK) + "fn f() -> u256 { |a }", "E_NOT_IN_USES"),
    ("warn", contract("    mut a: u256\n    mut b: u256\n", "        Get {} -> u256 uses (a, |b) { a }\n        Set { v } uses (mut a) { a = v }\n"), "E_UNUSED_USE"),
    ("warn", contract("    mut a: u256\n", ARMS_OK, "    init() uses (|mut a) { }\n"), "E_UNUSED_USE"),
    ("ok", contract("    mut a: u256\n", "        Get {} -> u256 uses (mut a) { a }\n        Set { v } uses (mut a) { a = v }\n")),
    ("err", contract("    mut a: u256\n", ARMS_OK, "    init(|a: u256) { }\n"), "N_SHADOWS_FIELD"),
    ("err", contract("    mut a: u256\n", "        Get {} -> u256 {\n            |let a: u256 = 1\n            a\n        }\n        Set { v } { }\n"), "N_SHADOWS_FIELD"),
    ("err", contract("    mut a: u256\n    mut |a: bool\n", ARMS_OK), "N_DUPLICATE"),
    ("err", "const a: u256 = 1\n" + contract("    mut |a: u256\n", ARMS_OK), "N_DUPLICATE"),
],
"selectors": [
    ("ok", "msg N {\n    #[selector = 0xffffffff]\n    A {},\n    #[selector = 0]\n    B {},\n}"),
    ("err", "msg N {\n    |#[selector = 0x100000000]\n    A {},\n}", "T_SELECTOR_TOO_LARGE"),
    ("err", "msg N {\n    #[selector = 1]\n    A {},\n    |#[selector = 0x01]\n    B {},\n}", "N_DUPLICATE_SELECTOR"),
    ("ok", contract("    mut a: u256\n", ARMS_OK, msgs="msg N {\n    #[selector = 0x03]\n    O {},\n}\n", recvs=RECV_N)),
    ("err", contract("    mut a: u256\n", ARMS_OK, msgs="msg N {\n    |#[selector = 0x02]\n    O {},\n}\n", recvs=RECV_N), "N_DUPLICATE_SELECTOR"),
],
"messages": [
    ("ok", contract("    mut a: u256\n", "        Set { v: w } uses (mut a) { a = w }\n" + GET_OK)),
    ("err", contract("    mut a: u256\n", GET_OK) .replace("    recv M", "    |recv M"), "N_MISSING_ARM"),
    ("err", contract("    mut a: u256\n", ARMS_OK + "        |Get {} -> u256 { 1 }\n"), "N_DUPLICATE"),
    ("err", contract("    mut a: u256\n", ARMS_OK + "        |Put {} { }\n"), "N_UNKNOWN_VARIANT"),
    ("err", contract("    mut a: u256\n", "        |Get {} uses (a) { }\n        Set { v } uses (mut a) { a = v }\n"), "T_MISMATCH"),
    ("err", contract("    mut a: u256\n", GET_OK + "        Set { |w } { }\n"), "N_UNKNOWN_FIELD"),
    ("err", contract("    mut a: u256\n", GET_OK + "        |Set {} { }\n"), "N_MISSING_BIND"),
    ("err", contract("    mut a: u256\n", GET_OK + "        Set { |v: a } { }\n"), "N_SHADOWS_FIELD"),
    ("err", "fn N() {}\n" + contract("", "").replace("recv M", "|recv N"), "N_NOT_A_MSG"),
    ("err", contract("    mut a: u256\n", ARMS_OK, recvs="    |recv M {\n" + ARMS_OK + "    }\n"), "N_DUPLICATE"),
    ("err", contract("    mut a: u256\n", GET_OK + "        Set { v } |{ true }\n"), "T_MISMATCH"),
],
}
codes = sorted({c[2] for g in groups.values() for c in g if c[0] != "ok"} | {"E_TOO_MANY_FIELDS"})
out = ["// Generated by tools/gen_check_tests.py. Edit the cases there and rerun it.",
       "// Tests for the checker: cases per rule of SPEC §2 and §4–6, each of which accepts, warns or",
       "// rejects. A warn or reject case names the diagnostic's code and the byte offset it points at.", "",
       "use ingot::ast::{TY_BOOL, TY_U256}", "use ingot::check::{Checked, check}",
       "use ingot::diag::{", *[f"    {c}," for c in codes], "    Diag,", "    DiagCode,", "}",
       "use ingot::io::{Source, text}", "use ingot::parser::{MAX_DEPTH, parse}",
       "use ingot::parser_tests::{DEEPEST_BLOCKS, DEEPEST_PARENS, Nested}", "use std::abi::DynString", "",
       "fn checked(_ s: DynString) -> Checked {", "    with (Source = text(s)) {", "        check(parse())", "    }", "}", "",
       "// Asserts that the checker accepts `s` without warnings.", "fn accepts(_ s: DynString) {", "    let c = checked(s)",
       "    assert!(c.err.is_none())", "    assert!(c.warns.len() == 0)", "}", "",
       "// Asserts that the checker accepts `s` with one warning, of `code` at byte `pos`.",
       "fn warns(_ s: DynString, _ code: DiagCode, _ pos: usize) {", "    let c = checked(s)", "    assert!(c.err.is_none())",
       "    assert!(c.warns.len() == 1)", "    assert!(c.warns[0].code == code)", "    assert!(c.warns[0].pos == pos)", "}", "",
       "fn rejects(_ s: DynString, _ code: DiagCode, _ pos: usize) {",
       "    let d = checked(s).err.unwrap()", "    assert!(d.code == code)", "    assert!(d.pos == pos)", "}"]
for name, cases in groups.items():
    out += ["", "#[test]", f"fn {name}() {{"]
    for c in cases:
        if c[0] == "ok":
            assert "|" not in c[1] or "||" in c[1], c
            out.append(f"    accepts({lit(c[1])})")
        else:
            src = c[1]
            i = src.index("|")
            src = src[:i] + src[i + 1:]
            helper = "warns" if c[0] == "warn" else "rejects"
            out.append(f"    {helper}({lit(src)}, {c[2]}, {i})")
    out.append("}")
SIDE = ("const A: u256 = 6 * 7\nfn f(_ p: u256) -> u256 {\n    let x = p + A\n    var y = x\n    y\n}\n"
        + contract("    mut a: u256\n    mut b: bool\n",
                   GET_OK + "        Set { v } uses (mut b) { b = v == A }\n"))
CHAIN = "fn f(_ c: bool) -> u256 { " + " else ".join(f"if c {{ {k} }}" for k in range(CHAIN_LEN)) + " else { 0 } }"
out += f"""
// The side tables that code generation reads.
#[test]
fn side_tables() {{
    let c = checked({lit(SIDE)})
    assert!(c.err.is_none())
    let items = c.ast.items
    let a = c.ast.list_at(items, 0)
    assert!(c.ast.words[c.slots[a]] == 42)
    // f has three frame slots: p, x and y.
    let f = c.ast.list_at(items, 1)
    assert!(c.slots[f] == 3)
    let k = c.ast.list_at(items, 3)
    let fields = c.ast.nodes[k].list()
    let b = c.ast.list_at(fields, 1)
    assert!(c.slots[b] == 1)
    assert!(c.types[b] == TY_BOOL)
    // In `Get`, the tail `a` resolves to field a.
    let recv = c.ast.list_at(c.ast.nodes[k].recvs(), 0)
    let get = c.ast.list_at(c.ast.nodes[recv].list(), 0)
    let tail = c.ast.nodes[c.ast.nodes[get].body()].value()
    assert!(c.res[tail] == c.ast.list_at(fields, 0))
    assert!(c.types[tail] == TY_U256)
    assert!(c.res[get] == c.ast.list_at(c.ast.nodes[c.res[recv]].list(), 0))
}}

fn nested(_ brackets: String<2>, _ depth: usize) -> Option<Diag> {{
    with (Source = Nested {{ brackets, depth, pos: 0 }}) {{
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
""".split("\n")
# A contract with more fields than the checker allows, generated by a Source so that the file
# holds no 257-line literal.
out += r'''
// A `Source` of a contract with `count` fields named f000, f001 and so on.
struct Fields { count: usize, pos: usize }

impl Source for Fields {
    fn next_byte(mut self) -> i32 {
        let head: String<13> = "contract K {\n"
        let line: String<19> = "    mut f000: u256\n"
        let tail: String<2> = "}\n"
        let digits: String<10> = "0123456789"
        let i = self.pos
        self.pos += 1
        if i < head.len() {
            return head.as_bytes()[i] as i32
        }
        let field = (i - head.len()) / line.len()
        let j = (i - head.len()) % line.len()
        if field < self.count {
            // Bytes 9 to 11 of a line are the field's three digits.
            if j >= 9 && j <= 11 {
                let place: usize = if j == 9 {
                    100
                } else if j == 10 { 10 } else { 1 }
                return digits.as_bytes()[field / place % 10] as i32
            }
            return line.as_bytes()[j] as i32
        }
        let k = i - head.len() - self.count * line.len()
        if k < tail.len() {
            return tail.as_bytes()[k] as i32
        }
        return -1
    }
}

fn fields(_ count: usize) -> Option<Diag> {
    with (Source = Fields { count, pos: 0 }) {
        check(parse()).err
    }
}

#[test]
fn too_many_fields() {
    assert!(fields(256).is_none())
    let d = fields(257).unwrap()
    assert!(d.code == E_TOO_MANY_FIELDS)
    // The name of field 256, after the 13-byte head and 256 lines of 19 bytes.
    assert!(d.pos == 13 + 256 * 19 + 8)
}
'''.rstrip("\n").split("\n")
write_formatted(FE0 / "src/check_tests.fe", "\n".join(out) + "\n")
