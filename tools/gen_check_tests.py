#!/usr/bin/env python3
"""Generate fe0/src/check_tests.fe and format it with fe fmt.

A case accepts, warns or rejects. A reject or warn case marks the position of its diagnostic
with `|`, and the script turns the mark into a byte offset. A mark is a `|` that is neither
part of `||` nor followed by whitespace. Every other `|` stays in the source. Change the cases
here and rerun the script, so the offsets stay right.

usage: [FE=path/to/fe] gen_check_tests.py
"""
import re
from dataclasses import KW_ONLY, dataclass, replace
from enum import Enum
from typing import Self

from fegen import (CHAIN_LEN, FE0, ByteOffset, FeLine, FeName, FeSource, TestName, lines, lit,
                   source, write_formatted)

MARK = re.compile(r"(?<!\|)\|(?![|\s])")


@dataclass(frozen=True)
class PointedSource:
    """A Fe source and the byte in it that a diagnostic points at."""

    src: FeSource
    at: ByteOffset

    @classmethod
    def parse(cls, marked: str) -> Self:
        marks = [m.start() for m in MARK.finditer(marked)]
        if len(marks) != 1:
            raise ValueError(f"Found {len(marks)} marks in {marked!r}. A diagnosed case needs"
                             " exactly one.")
        i = marks[0]
        return cls(FeSource(marked[:i] + marked[i + 1:]), ByteOffset(len(marked[:i].encode())))

    @staticmethod
    def unmarked(src: str) -> FeSource:
        if MARK.search(src):
            raise ValueError(f"Found a mark in {src!r}. An accepted case has no diagnostic to"
                             " point at.")
        return FeSource(src)


class Helper(Enum):
    """The function of check_tests.fe that checks a case. Its value is the function's name."""

    ACCEPTS = "accepts"
    WARNS = "warns"
    REJECTS = "rejects"

    def call(self, *args: object) -> FeLine:
        return FeLine(f"    {self.value}({', '.join(map(str, args))})")


@dataclass(frozen=True)
class Accepts:
    """A case that the checker accepts without warnings."""

    src: FeSource

    def line(self) -> FeLine:
        return Helper.ACCEPTS.call(lit(self.src))


@dataclass(frozen=True)
class Diagnosed:
    """A case that the checker warns about or rejects, with the constant of fe0/src/diag.fe that
    names the diagnostic's code."""

    helper: Helper
    pointed: PointedSource
    code: FeName

    def line(self) -> FeLine:
        return self.helper.call(lit(self.pointed.src), self.code, self.pointed.at)


Case = Accepts | Diagnosed


def text(src: str | ContractCase) -> str:
    return src if isinstance(src, str) else src.source()


def ok(src: str | ContractCase) -> Accepts:
    return Accepts(PointedSource.unmarked(text(src)))


def warn(src: str | ContractCase, code: str) -> Diagnosed:
    """Returns a case that the checker warns about with the diagnostic `code`."""
    return Diagnosed(Helper.WARNS, PointedSource.parse(text(src)), FeName(code))


def err(src: str | ContractCase, code: str) -> Diagnosed:
    """Returns a case that the checker rejects with the diagnostic `code`."""
    return Diagnosed(Helper.REJECTS, PointedSource.parse(text(src)), FeName(code))


# The msg that every contract case receives.
MSG = "msg M {\n    #[selector = 0x01]\n    Get -> u256,\n    #[selector = 0x02]\n    Set { v: u256 },\n}\n"
FIELD_A = "    mut a: u256\n"
GET_OK = "        Get {} -> u256 uses (a) { a }\n"
ARMS_OK = GET_OK + "        Set { v } uses (mut a) { a = v }\n"
# The fields of the maps cases. FIELD_A stays because GET_OK reads it.
MAPS = FIELD_A + "    mut m: StorageMap<Address, u256>\n    mut f: StorageMap<u256, bool>\n"
@dataclass(frozen=True)
class ContractCase:
    """A program of `items`, MSG and `msgs`, then contract K, whose recv block opens with
    `recv_head` and holds the arms `arms`. Its `uses` clause is left out when `effects` is
    empty."""

    arms: str
    fields: str = FIELD_A
    _: KW_ONLY
    init: str = ""
    msgs: str = ""
    recvs: str = ""
    effects: str = ""
    items: str = ""
    recv_head: str = "recv M"

    def source(self) -> str:
        uses = f"uses ({self.effects}) " if self.effects else ""
        return (self.items + MSG + self.msgs + "contract K " + uses + "{\n" + self.fields + self.init
                + "    " + self.recv_head + " {\n" + self.arms + "    }\n" + self.recvs + "}\n")
def set_arm(body: str, fields: str = FIELD_A) -> ContractCase:
    """Returns the contract whose arms are GET_OK and a Set arm with the text `body` after
    `Set { v } `."""
    return ContractCase(GET_OK + "        Set { v } " + body + "\n", fields)
def event(name: str, *fields: str) -> str:
    """Returns the source of an event struct. Write each entry of `fields` without its comma."""
    body = "".join(f"    {f},\n" for f in fields)
    return f"#[event]\nstruct {name} {{" + ("\n" + body if fields else "") + "}\n"
def indexed(field: str) -> str:
    return "#[indexed]\n    " + field
RECV_N = "    recv N {\n        O {} { }\n    }\n"
CTX = "ctx: Ctx"
LOG = "log: mut Log"
LOG_RO = "log: Log"
def ctx_arm(body: str) -> ContractCase:
    return replace(set_arm(body), effects=CTX)
# The event that the events cases emit.
EVENT = event("E", indexed("to: Address"), "amount: u256")
def log_arm(body: str, items: str = EVENT, effects: str = LOG + ", " + CTX) -> ContractCase:
    return replace(set_arm(body), items=items, effects=effects)
def emit_ok(effect: str = "log", amount: str = "v") -> str:
    """Returns a statement that emits EVENT. The statement reads `ctx.caller()`, so its body needs
    the Ctx effect."""
    return f"{effect}.emit(E {{ to: ctx.caller(), amount: {amount} }})"
# The msg of another contract, which the msg_calls cases call.
OTHER = "msg O {\n    #[selector = 0x11]\n    Echo { a: u256 } -> u256,\n    #[selector = 0x12]\n    Put { a: u256 },\n}\n"
CALL_FIELDS = FIELD_A + "    mut t: Address\n"
CALL = "call: mut Call"
CALL_RO = "call: Call"
CALL_CTX = CALL + ", " + CTX
def call_arm(body: str, effects: str = CALL) -> ContractCase:
    return replace(set_arm(body, CALL_FIELDS), items=OTHER, effects=effects)
groups: dict[TestName, list[Case]] = {
TestName("types_of_operators"): [
    ok("fn f(_ a: u256, _ b: bool, _ c: Address, _ d: Address) -> bool {\n    a + 1 * 2 / 3 % 4 & 5 | 6 ^ 7 << 8 >> 9 > 0 && !b || c == d && ~a != 0\n}"),
    ok("fn f(_ a: u256) -> bool { a < 1 || a <= 1 || a > 1 || a >= 1 }"),
    err("fn f(_ b: bool) -> u256 { |b + 1 }", "T_MISMATCH"),
    err("fn f(_ a: u256) -> bool { |a && true }", "T_MISMATCH"),
    err("fn f(_ a: Address, _ b: Address) -> bool { |a < b }", "T_MISMATCH"),
    err("fn f(_ a: u256) -> bool { a == |true }", "T_MISMATCH"),
    # A chain of comparisons reads from the left, so its types must fit (SPEC.md §3.2).
    ok("fn f(_ a: u256, _ b: u256) -> bool { a < b == true }"),
    ok("fn f(_ a: u256, _ b: u256) -> bool { a == b != (b == a) }"),
    err("fn f(_ a: u256, _ b: u256, _ c: u256) -> bool { a |< b < c }", "T_MISMATCH"),
    err("fn f(_ a: u256) -> bool { !|a }", "T_MISMATCH"),
    err("fn f(_ b: bool) -> bool { ~|b }", "T_MISMATCH"),
    err("fn f(_ b: bool) -> bool { +|b }", "T_MISMATCH"),
    err("fn f(_ c: Address) -> Address { +|c }", "T_MISMATCH"),
    ok("fn f(_ a: u256) -> u256 { +a + +1 }"),
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
    ok("fn f(_ Option: u256, X: u256) -> u256 { Option + X }"),
    err(ContractCase(GET_OK + "        Set { |v: Ok } { }\n"), "N_UPPERCASE_LOCAL"),
    err("fn f() -> u256 {\n    |var Foo: u256 = 1\n    Foo\n}", "N_UPPERCASE_LOCAL"),
    err(ContractCase(GET_OK + "        Set { |v: n } { }\n", items="const n: u256 = 5\n"), "N_LOCAL_AS_PATTERN"),
    err("const n: u256 = 5\nfn f() -> u256 {\n    |let n: u256 = 2\n    n\n}", "N_LOCAL_AS_PATTERN"),
    err(event("e") + "fn f() -> u256 {\n    |let e: u256 = 2\n    e\n}", "N_LOCAL_AS_PATTERN"),
    err("contract k {\n}\nfn f() -> u256 {\n    |var k: u256 = 2\n    k\n}", "N_LOCAL_AS_PATTERN"),
    # Fe accepts a local named like a function or a msg, and a parameter named like any item.
    ok("fn g() -> u256 { 1 }\nfn f() -> u256 {\n    let g: u256 = 2\n    g\n}\nfn h() -> u256 { g() }"),
    ok("msg m {\n    #[selector = 0x01]\n    A {},\n}\nfn f() -> u256 {\n    let m: u256 = 2\n    m\n}"),
    ok("const n: u256 = 5\n" + event("e") + "contract k {\n}\nfn f(_ n: u256, _ e: u256, _ k: u256) -> u256 { n + e + k }"),
    err("fn g() -> u256 { 1 }\nfn f(_ g: u256) -> u256 { |g() }", "N_NOT_A_FUNCTION"),
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
    ok("const A: u256 = 2 + 3\nconst B: u256 = A * 4 - 1 / 1 % 7\nconst C: bool = B == 19 && !false\nconst D: u256 = 1 << 256\nconst E: u256 = ~+2 - +A"),
    ok("const A: u256 = B * C\nconst B: u256 = C + 1\nconst C: u256 = 3\nfn f() -> u256 { A }"),
    err("const A: u256 = |B\nconst B: u256 = A", "N_CONST_CYCLE"),
    err("const A: u256 = |A", "N_CONST_CYCLE"),
    err("const C: u256 = |A\nconst A: u256 = B\nconst B: u256 = A", "N_CONST_CYCLE"),
    err("const A: u256 = B |+ 1\nconst B: u256 = 0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", "C_OVERFLOW"),
    err("const A: u256 = 0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff |+ 1", "C_OVERFLOW"),
    err("const A: u256 = 0 |- 1", "C_OVERFLOW"),
    err("const A: u256 = 0x8000000000000000000000000000000000000000000000000000000000000000 |* 2", "C_OVERFLOW"),
    err("const A: u256 = 1 |/ 0", "C_DIV_ZERO"),
    err("const A: u256 = 1 |% 0", "C_DIV_ZERO"),
    err("fn g() -> u256 { 1 }\nconst A: u256 = |g()", "C_NOT_CONST"),
    err("const A: bool = |1", "T_MISMATCH"),
    err("const A: u256 = 1 + |true", "T_MISMATCH"),
    err("const A: u256 = +|true", "T_MISMATCH"),
],
TestName("effects"): [
    ok(ContractCase(ARMS_OK, init="    init(x: u256) uses (mut a) { a = x }\n")),
    err(ContractCase("        Get {} -> u256 { |a }\n        Set { v } uses (mut a) { a = v }\n"), "E_NOT_IN_USES"),
    err(set_arm("uses (a) { |a = v }"), "E_NOT_MUT"),
    err(set_arm("uses (a) { |a += v }"), "E_NOT_MUT"),
    err(ContractCase("        Get {} -> u256 uses (|b) { 1 }\n        Set { v } { }\n"), "E_UNKNOWN_FIELD"),
    err(set_arm("uses (a, |mut a) { a = v }"), "N_DUPLICATE"),
    err(set_arm("uses (mut a, |a) { a = v }"), "N_DUPLICATE"),
    err(ContractCase(ARMS_OK).source() + "fn f() -> u256 { |a }", "E_NOT_IN_USES"),
    warn(ContractCase("        Get {} -> u256 uses (a, |b) { a }\n        Set { v } uses (mut a) { a = v }\n", FIELD_A + "    mut b: u256\n"), "E_UNUSED_USE"),
    warn(ContractCase(ARMS_OK, init="    init() uses (|mut a) { }\n"), "E_UNUSED_USE"),
    ok(ContractCase("        Get {} -> u256 uses (mut a) { a }\n        Set { v } uses (mut a) { a = v }\n")),
    err(ContractCase(ARMS_OK, init="    init(|a: u256) uses (mut a) { a = 1 }\n"), "N_NAMED_LIKE_USE"),
    ok(ContractCase(ARMS_OK, init="    init(a: u256) { }\n")),
    ok(ContractCase("        Get {} -> u256 uses (a) {\n            let a: u256 = a + 1\n            a\n        }\n        Set { v } { }\n")),
    err(ContractCase(ARMS_OK, FIELD_A + "    mut |a: bool\n"), "N_DUPLICATE"),
    err(ContractCase(ARMS_OK, "    mut |a: u256\n", items="const a: u256 = 1\n"), "N_DUPLICATE"),
    ok(ctx_arm("uses (mut a, ctx) {\n            assert!(ctx.origin() == ctx.coinbase())\n            a = ctx.block_number() + ctx.chainid() + ctx.gasprice() + ctx.prevrandao() + ctx.gaslimit() + ctx.basefee() + ctx.blobbasefee()\n        }")),
    err(ctx_arm("uses (ctx) { assert!(|ctx.timestamp() == 0) }"), "N_UNKNOWN_NAME"),
    err(ctx_arm("uses (ctx) { assert!(ctx.chainid() == |ctx.caller()) }"), "T_MISMATCH"),
],
TestName("maps"): [
    ok(set_arm("uses (mut m, mut f) {\n            m[Address::zero()] += v\n            f[v] = !f[m[Address::zero()] + 1]\n        }", MAPS)),
    err(set_arm("{ assert!(|m[Address::zero()] == v) }", MAPS), "E_NOT_IN_USES"),
    err(set_arm("uses (m) { |m[Address::zero()] = v }", MAPS), "E_NOT_MUT"),
    err(set_arm("uses (m) { let x = |m }", MAPS), "N_NOT_A_VALUE"),
    err(set_arm("uses (mut m) { |m = v }", MAPS), "N_ASSIGN_IMMUTABLE"),
    err(ContractCase("        Get {} -> u256 uses (a) { |a[1] }\n        Set { v } { }\n", MAPS), "T_MISMATCH"),
    err(set_arm("uses (mut a) { |a[v] = v }", MAPS), "T_MISMATCH"),
    err(set_arm("uses (mut m) { m[|v] = v }", MAPS), "T_MISMATCH"),
    err(set_arm("uses (mut f) { f[v] = |v }", MAPS), "T_MISMATCH"),
    err(set_arm("uses (mut f) { |f[v] += true }", MAPS), "T_MISMATCH"),
    err(set_arm("{ |g[v] = v }", MAPS), "N_UNKNOWN_NAME"),
],
TestName("events"): [
    ok(log_arm("uses (mut log, ctx) { " + emit_ok() + " }")),
    ok(log_arm("uses (mut log) {\n            let to = Address::zero()\n            log.emit(E { amount: v + 1, to })\n        }")),
    ok(replace(log_arm("{ }"), init="    init() uses (mut log, ctx) { " + emit_ok(amount="1") + " }\n")),
    ok(log_arm("uses (mut l2, ctx) { " + emit_ok("l2") + " }", effects=LOG + ", l2: mut Log, " + CTX)),
    ok(log_arm("uses (mut log) { log.emit(D {}) }", EVENT + event("D"))),
    ok(log_arm("uses (log, ctx) { " + emit_ok() + " }")),
    err(log_arm("uses (ctx) { |" + emit_ok() + " }"), "E_NOT_IN_USES"),
    ok(log_arm("uses (mut log, ctx) { " + emit_ok() + " }", effects=LOG + ", quiet: Log, " + CTX)),
    err(log_arm("uses (log, ctx) { |" + emit_ok() + " }", effects=LOG_RO + ", " + CTX), "E_EFFECT_NOT_MUT"),
    err(log_arm("uses (mut log, ctx) { |" + emit_ok() + " }", effects=LOG_RO + ", " + CTX), "E_EFFECT_NOT_MUT"),
    err(log_arm("uses (log) { assert!(|log.caller() == Address::zero()) }", effects=LOG_RO), "T_MISMATCH"),
    err(log_arm("uses (mut log, ctx) { |" + emit_ok("ctx") + " }"), "T_MISMATCH"),
    err(log_arm("uses (mut log) { assert!(|log.caller() == Address::zero()) }"), "T_MISMATCH"),
    err(log_arm("uses (mut log) { let x = |log }"), "N_NOT_A_VALUE"),
    err(log_arm("uses (mut log) { |log.emit(M { amount: v }) }"), "T_MISMATCH"),
    err(log_arm("uses (mut log) { |log.emit(F { amount: v }) }"), "N_UNKNOWN_NAME"),
    err(log_arm("uses (mut log) { |log.emit(E { amount: v }) }"), "N_MISSING_FIELD"),
    err(log_arm("uses (mut log) { log.emit(E { to: Address::zero(), amount: v, |amount: v }) }"), "N_DUPLICATE"),
    err(log_arm("uses (mut log) { log.emit(E { to: Address::zero(), |c: v }) }"), "N_UNKNOWN_FIELD"),
    err(log_arm("uses (mut log) { log.emit(E { to: Address::zero(), |v + 1 }) }"), "N_UNKNOWN_FIELD"),
    err(log_arm("uses (mut log) { log.emit(E { to: |v, amount: v }) }"), "T_MISMATCH"),
    err(log_arm("uses (mut log, ctx) { let x = |" + emit_ok() + " }"), "T_NO_VALUE"),
    err(log_arm("{ let x = |E }"), "N_NOT_A_VALUE"),
    err(log_arm("{ |E() }"), "N_NOT_A_FUNCTION"),
    err(log_arm("{ }").source() + "fn f() { |log.emit(E { to: Address::zero(), amount: 1 }) }", "E_NOT_IN_USES"),
    err(log_arm("{ }", event("E", "to: u256", "|to: u256")), "N_DUPLICATE"),
    err(log_arm("{ }").source() + "#[event]\n|struct M {}", "N_DUPLICATE"),
    ok(log_arm("{ }", event("E", *(indexed(f"a{k}: u256") for k in range(3)), "b: u256"))),
    err(log_arm("{ }", event("E", "b: u256", *(indexed(f"a{k}: bool") for k in range(3)),
                        indexed("|a3: bool"))), "T_TOO_MANY_INDEXED"),
],
TestName("msg_calls"): [
    ok(call_arm("uses (t, mut call) { t.call(O::Put { a: v }) }")),
    ok(call_arm("uses (mut a, t, mut call) { a = t.call(O::Echo { a: v + 1 }) }")),
    ok(call_arm("uses (mut call, ctx) {\n            let to = ctx.caller()\n            to.call(O::Put { a: v })\n        }", effects=CALL_CTX)),
    ok(call_arm("uses (mut a, t, mut call) { a = t.call(O::Echo { a: t.call(O::Echo { a: v }) }) }")),
    ok(call_arm("uses (t, mut call) { t.call(M::Set { v }) }")),
    ok(replace(call_arm("{ }"), init="    init(to: Address) uses (mut call) { to.call(O::Put { a: 1 }) }\n")),
    warn(call_arm("uses (|mut call) { }"), "E_UNUSED_USE"),
    ok(call_arm("uses (t, call) { t.call(O::Put { a: v }) }")),
    err(call_arm("uses (t) { |t.call(O::Put { a: v }) }"), "E_NOT_IN_USES"),
    err(call_arm("uses (t) { |t.call(O::Put { a: v }) }", effects=CTX), "E_NOT_IN_USES"),
    err(call_arm("uses (mut call) { |t.call(O::Put { a: v }) }"), "E_NOT_IN_USES"),
    err(call_arm("{ }", effects=CALL + ", |c2: mut Call"), "N_DUPLICATE"),
    err(call_arm("{ }", effects=CALL_RO + ", |c2: mut Call"), "N_DUPLICATE"),
    ok(call_arm("{ }", effects=CALL_RO)),
    err(call_arm("uses (t) { |t.call(O::Put { a: v }) }", effects=CALL_RO), "E_NOT_IN_USES"),
    err(call_arm("uses (t, call) { |t.call(O::Put { a: v }) }", effects=CALL_RO), "E_EFFECT_NOT_MUT"),
    err(call_arm("uses (t, mut call) { |t.call(O::Put { a: v }) }", effects=CALL_RO), "E_EFFECT_NOT_MUT"),
    err(call_arm("uses (call) { assert!(|call.caller() == Address::zero()) }", effects=CALL_RO), "T_MISMATCH"),
    err(call_arm("uses (mut call) { |v.call(O::Put { a: v }) }"), "T_MISMATCH"),
    err(call_arm("uses (mut call) { |call.call(O::Put { a: v }) }"), "N_NOT_A_VALUE"),
    err(call_arm("uses (mut call) { let x = |call }"), "N_NOT_A_VALUE"),
    err(call_arm("uses (call) { assert!(|call.caller() == Address::zero()) }"), "T_MISMATCH"),
    ok(call_arm("uses (mut call, ctx) {\n            let me = ctx.address()\n            me.call(M::Set { v })\n        }", effects=CALL_CTX)),
    err(call_arm("uses (mut call) { assert!(|ctx.address() == t) }", effects=CALL_CTX), "E_NOT_IN_USES"),
    err(call_arm("uses (call) { assert!(|call.address() == Address::zero()) }"), "T_MISMATCH"),
    err(call_arm("uses (t, mut call) { |t.call(P::Put { a: v }) }"), "N_UNKNOWN_NAME"),
    err(call_arm("uses (t, mut call) { |t.call(f::Put { a: v }) }").source() + "fn f() {}", "N_NOT_A_MSG"),
    err(call_arm("uses (t, mut call) { |t.call(O::Get { a: v }) }"), "N_UNKNOWN_VARIANT"),
    err(call_arm("uses (t, mut call) { |t.call(O::Put {}) }"), "N_MISSING_FIELD"),
    err(call_arm("uses (t, mut call) { t.call(O::Put { a: v, |a: v }) }"), "N_DUPLICATE"),
    err(call_arm("uses (t, mut call) { t.call(O::Put { a: v, |b: v }) }"), "N_UNKNOWN_FIELD"),
    err(call_arm("uses (t, mut call) { t.call(O::Put { a: |true }) }"), "T_MISMATCH"),
    err(call_arm("uses (t, mut call) { let x = |t.call(O::Put { a: v }) }"), "T_NO_VALUE"),
    err(call_arm("{ }").source() + "fn f(_ to: Address) { |to.call(O::Put { a: 1 }) }", "E_NOT_IN_USES"),
],
TestName("selectors"): [
    ok("msg N {\n    #[selector = 0xffffffff]\n    A {},\n    #[selector = 0]\n    B {},\n}"),
    err("msg N {\n    |#[selector = 0x100000000]\n    A {},\n}", "T_SELECTOR_TOO_LARGE"),
    err("msg N {\n    #[selector = 1]\n    A {},\n    |#[selector = 0x01]\n    B {},\n}", "N_DUPLICATE_SELECTOR"),
    ok(ContractCase(ARMS_OK, msgs="msg N {\n    #[selector = 0x03]\n    O {},\n}\n", recvs=RECV_N)),
    err(ContractCase(ARMS_OK, msgs="msg N {\n    |#[selector = 0x02]\n    O {},\n}\n", recvs=RECV_N), "N_DUPLICATE_SELECTOR"),
],
TestName("messages"): [
    ok(ContractCase("        Set { v: w } uses (mut a) { a = w }\n" + GET_OK)),
    err(ContractCase(GET_OK, recv_head="|recv M"), "N_MISSING_ARM"),
    err(ContractCase(ARMS_OK + "        |Get {} -> u256 { 1 }\n"), "N_DUPLICATE"),
    err(ContractCase(ARMS_OK + "        |Put {} { }\n"), "N_UNKNOWN_VARIANT"),
    err(ContractCase("        |Get {} uses (a) { }\n        Set { v } uses (mut a) { a = v }\n"), "T_MISMATCH"),
    err(ContractCase(GET_OK + "        Set { |w } { }\n"), "N_UNKNOWN_FIELD"),
    err(ContractCase(GET_OK + "        |Set {} { }\n"), "N_MISSING_BIND"),
    err(ContractCase(GET_OK + "        Set { |v: a } uses (mut a) { a = 1 }\n"), "N_NAMED_LIKE_USE"),
    ok(ContractCase(GET_OK + "        Set { v: a } { }\n")),
    err("fn N() {}\n" + ContractCase("", "", recv_head="|recv N").source(), "N_NOT_A_MSG"),
    err(ContractCase(ARMS_OK, recvs="    |recv M {\n" + ARMS_OK + "    }\n"), "N_DUPLICATE"),
    err(set_arm("|{ true }"), "T_MISMATCH"),
],
}
TOO_MANY_FIELDS = FeName("E_TOO_MANY_FIELDS")
codes = sorted({c.code for g in groups.values() for c in g if isinstance(c, Diagnosed)}
               | {TOO_MANY_FIELDS})
code_uses = "\n".join(f"    {c}," for c in codes)
out = lines(FeSource(f"""// Generated by tools/gen_check_tests.py. Edit the cases there and rerun it.
// Tests the checker on the rules of SPEC §2 and §4 to §6 (DESIGN.md §13).

use ingot::ast::{{TY_BOOL, TY_U256}}
use ingot::check::{{CheckOutput, Const, Event, MAX_FIELDS, check, decl}}
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

fn checked(_ s: own DynString) -> CheckOutput {{
    with (Source = text(s)) {{
        check(parse())
    }}
}}

// Asserts that the checker finds no error in `s`, and returns what it found.
fn passes(_ s: own DynString) -> CheckOutput {{
    let out = checked(s)
    assert!(out.err.is_none())
    out
}}

// Asserts that the checker accepts `s` without warnings.
fn {Helper.ACCEPTS.value}(_ s: own DynString) {{
    assert!(passes(s).warns.len() == 0)
}}

// Asserts that the checker accepts `s` with one warning, of `code` at byte `pos`.
fn {Helper.WARNS.value}(_ s: own DynString, _ code: DiagCode, _ pos: usize) {{
    let c = passes(s)
    assert!(c.warns.len() == 1)
    assert!(c.warns[0].code == code)
    assert!(c.warns[0].pos() == Pos::at(pos))
}}

fn {Helper.REJECTS.value}(_ s: own DynString, _ code: DiagCode, _ pos: usize) {{
    let d = checked(s).err.unwrap()
    assert!(d.code == code)
    assert!(d.pos() == Pos::at(pos))
}}"""))
for name, cases in groups.items():
    out += [FeLine(""), FeLine("#[test]"), FeLine(f"fn {name}() {{")] + [c.line() for c in cases]
    out.append(FeLine("}"))
SIDE = ("const A: u256 = 6 * 7\nfn f(_ p: u256) -> u256 {\n    let x = p + A\n    var y = x\n    y\n}\n"
        + set_arm("uses (mut b) { b = v == A }", FIELD_A + "    mut b: bool\n").source())
PLACES = ContractCase("        Get {} -> u256 uses (d) { d }\n        Set { v } uses (mut d) { d = v }\n",
                      "    mut a: Address\n    mut b: bool\n    mut c: Address\n    mut d: u256\n"
                      "    mut e: bool\n").source()
# The standard ERC20 Transfer event, and an event with no fields.
EVENTS = (event("Transfer", indexed("from: Address"), indexed("to: Address"), "value: u256")
          + event("Empty"))
CHAIN = "fn f(_ c: bool) -> u256 { " + " else ".join(f"if c {{ {k} }}" for k in range(CHAIN_LEN)) + " else { 0 } }"
out += lines(FeSource(f"""
// The side tables that code generation reads.
#[test]
fn side_tables() {{
    let c = passes({lit(SIDE)}).program
    let items = c.ast.items
    let a = c.ast.list_at(items, 0)
    assert!(c.word_of(c.narrow<Const>(decl(a)).unwrap()) == 42)
    // f has three frame slots: p, x and y.
    let f = c.ast.list_at(items, 1)
    assert!(c.frame_slots(f) == 3)
    let fields = c.contract_fields()
    let b = fields.at(c.ast, 1)
    assert!(c.storage_place(b).slot() == 1)
    assert!(c.storage_place(b).whole())
    assert!(c.ty(b.node_id()) == TY_BOOL)
    // In `Get`, the tail `a` resolves to field a.
    let recv = c.ast.list_at(c.contract_node().recvs(), 0)
    let get = c.ast.list_at(c.ast.node(recv).list(), 0)
    let tail = c.ast.node(c.ast.node(get).body()).value()
    assert!(c.declaration(tail).node_id() == fields.at(c.ast, 0).node_id())
    assert!(c.ty(tail) == TY_U256)
    assert!(c.variant_of(get).node_id() == c.ast.list_at(c.ast.node(c.msg_of(recv).node_id()).list(), 0))
}}

// Fields narrower than a slot share one, in declaration order from the low end (SPEC §6).
#[test]
fn storage_places() {{
    let c = passes({lit(PLACES)}).program
    let fields = c.contract_fields()
    let a = c.storage_place(fields.at(c.ast, 0))
    assert!(a.slot() == 0 && a.shift() == 0 && a.shared_above() && !a.whole())
    let b = c.storage_place(fields.at(c.ast, 1))
    assert!(b.slot() == 0 && b.shift() == 160 && !b.shared_above() && b.mask() == 0xff)
    // c's 20 bytes do not fit in the 11 left in slot 0.
    let c2 = c.storage_place(fields.at(c.ast, 2))
    assert!(c2.slot() == 1 && c2.whole())
    let d = c.storage_place(fields.at(c.ast, 3))
    assert!(d.slot() == 2 && d.whole())
    // A field after a u256 starts a new slot.
    let e = c.storage_place(fields.at(c.ast, 4))
    assert!(e.slot() == 3 && e.whole())
}}

// The log of an event (SPEC §6, "Events") and the LogWord of each of its fields.
#[test]
fn event_words() {{
    let c = passes({lit(EVENTS)}).program
    let e = c.narrow<Event>(decl(c.ast.list_at(c.ast.items, 0))).unwrap()
    assert!(c.topic0(e) == 0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef)
    assert!(c.data_words(e) == 1)
    let fields = c.event_fields(e)
    assert!(c.log_word(fields.at(c.ast, 0)).number() == 1)
    assert!(c.log_word(fields.at(c.ast, 1)).number() == 2)
    assert!(c.log_word(fields.at(c.ast, 2)).number() == 0)
    let empty = c.narrow<Event>(decl(c.ast.list_at(c.ast.items, 1))).unwrap()
    // keccak("Empty()")
    assert!(c.topic0(empty) == 0x3db2a12a1fcfb6e2e0de8666c64b3244166edb7b25b200204a8d0cca9b65cf37)
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
}'''))
out += lines(FeSource(f"""
#[test]
fn too_many_fields() {{
    assert!(fields(MAX_FIELDS).is_none())
    let d = fields(MAX_FIELDS + 1).unwrap()
    assert!(d.code == {TOO_MANY_FIELDS})
    // The error points at the name of the extra field.
    assert!(d.pos() == Pos::at(FIELDS_HEAD.len() + MAX_FIELDS * FIELD_LINE.len() + FIELD_NAME_AT))
}}"""))
write_formatted(FE0 / "src/check_tests.fe", source(out))
