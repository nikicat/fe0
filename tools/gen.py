#!/usr/bin/env python3
"""Generate random Fe0 programs and run them through the differential harness (DESIGN.md §11).

Each seed gives one program, `corpus/gen/s<seed>.fe`, and its call script `s<seed>.calls`, in
the format that tools/embed.py reads. The same seed always gives the same files, so a failure
names the seed and `gen.py --seed <seed> -n 1` reproduces it.

A program has 0–3 constants, 0–3 pure helper functions, one or two msgs and one contract with
1–4 `mut` fields. Each arm lists the fields it uses, sometimes with unused extra entries. The
expressions are random trees over u256, bool and Address that use every operator of SPEC.md §4,
if-expressions, blocks and helper calls with positional and labelled arguments. Literals lean
towards edge values such as 0, 2**255 and MAX, so that checked arithmetic fails now and then.
They come in decimal, `_`-grouped and hex forms.

The call script has an `init` line, 0–2 more `deploy` lines and 5–20 calls. Nearly a third of
the deploy and call lines are malformed. They miss a word, give a bool word of 2 or MAX, set
high bits in an Address word or send a value in wei. Some lines carry extra bytes.

The generated programs never loop forever and never run out of gas:
- A loop is `var n: u256 = 0` and `while n < K`, with K at most 8. Its body either ends with
  `n += 1` or starts with it, and only the latter kind holds `continue`. Nothing else assigns n.
- Loops nest at most two deep in an arm, and a helper has at most one loop.
- A helper calls only helpers written before it, so there is no recursion. Inside a loop, code
  calls only helpers without loops.
- `init` leaves out the operators that can fail, asserts and helper calls, so the main
  deployment always creates a contract.

With --no-run, it still writes the programs and runs fe check on them.
"""
import random
import re
import shutil
from collections.abc import Callable, Collection, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from pathlib import Path
from typing import NamedTuple

import embed
from embed import Args, DeployLine, InitLine, NamedCallLine, ScriptLine
from fegen import MAX, PROBE_SELECTOR, ROOT, FeLine, FeName, FeSource, Selector, Wei, Word, indent

GEN: Path = ROOT / "corpus/gen"
OUT: Path = ROOT / "out/gen"


class Ty(StrEnum):
    """A Fe0 type. Its value is its name in Fe."""

    U256 = "u256"
    BOOL = "bool"
    ADDRESS = "Address"


# Binding powers, loosest first (SPEC.md §3.2). IF covers if-expressions and blocks, which are
# put in parentheses wherever an operand stands.
IF, OR, AND, CMP, BITOR, BITXOR, BITAND, SHIFT, ADD, MUL, UNARY, ATOM = range(12)


def checked(v: int) -> int | None:
    """`v`, or None when it is not a u256."""
    return v if 0 <= v <= MAX else None


class Op(NamedTuple):
    """A binary u256 operator."""

    symbol: str
    prec: int
    # Whether it can fail (SPEC.md §4).
    fails: bool
    # The value of `a op b`, or None when it fails.
    evaluate: Callable[[int, int], int | None]

    @property
    def is_shift(self) -> bool:
        return self.prec == SHIFT


OPS: list[Op] = [
    Op("|", BITOR, False, lambda a, b: a | b),
    Op("^", BITXOR, False, lambda a, b: a ^ b),
    Op("&", BITAND, False, lambda a, b: a & b),
    Op("<<", SHIFT, False, lambda a, b: (a << b) & MAX if b < 256 else 0),
    Op(">>", SHIFT, False, lambda a, b: a >> b if b < 256 else 0),
    Op("+", ADD, True, lambda a, b: checked(a + b)),
    Op("-", ADD, True, lambda a, b: checked(a - b)),
    Op("*", MUL, True, lambda a, b: checked(a * b)),
    Op("/", MUL, True, lambda a, b: a // b if b else None),
    Op("%", MUL, True, lambda a, b: a % b if b else None),
]
CMP_OPS = ["==", "!=", "<", ">", "<=", ">="]
# Outside constant declarations, every shift amount that is not a literal is masked with this.
SHIFT_MASK = 0x1ff
EDGES = [0, 1, 2, 255, 256, 2**128, 2**255, MAX - 1, MAX]
MAX_LOOP = 8
# How deep loops nest in a helper, and in init or an arm.
MAX_HELPER_LOOP_DEPTH = 1
MAX_LOOP_DEPTH = 2


class E(NamedTuple):
    """An expression's text, with how tightly it binds."""

    text: str
    prec: int
    # Whether it has a type of its own. A u256 expression of only literals, operators,
    # if-expressions and blocks does not (SPEC.md §2), so it cannot be compared with another
    # such expression.
    typed: bool = True

    def at(self, prec: int) -> str:
        """The text as an operand that must bind at least as tightly as `prec`."""
        return self.parenthesized().text if self.prec < prec else self.text

    def parenthesized(self) -> "E":
        """The expression in parentheses, which binds as an atom."""
        return self._replace(text=f"({self.text})", prec=ATOM)

    def may_take_generics(self) -> bool:
        """Checks whether a `<` after the expression may start generic arguments (SPEC.md §3.2).
        If it may, the expression needs parentheses. This test returns true in more cases than
        Fe0's rule."""
        return self.text[-1].isalnum() or self.text[-1] == "_"

    def may_read_as_record(self) -> bool:
        """Whether the expression, as a line of its own, may read as a record literal of the line
        before it (SPEC.md §3.4)."""
        return self.text.startswith("{")


class VarKind(StrEnum):
    CONST = "const"
    PARAM = "param"
    LET = "let"
    VAR = "var"
    # A loop's counter.
    COUNTER = "counter"
    FIELD = "field"


class Var(NamedTuple):
    name: FeName
    ty: Ty
    kind: VarKind


class ConstExpr(NamedTuple):
    """A u256 expression of literals and constants, with its value."""

    expr: E
    value: Word


class Const(NamedTuple):
    """A u256 constant, with its value."""

    name: FeName
    value: Word


class Scope(list[Var]):
    """The variables that code can use at one point."""

    def of(self, ty: Ty, kinds: Collection[VarKind] | None = None) -> list[Var]:
        """The variables of type `ty`, and of one of `kinds` when it is given."""
        return [v for v in self if v.ty == ty and (kinds is None or v.kind in kinds)]

    def assignable(self) -> list[Var]:
        """The variables that code can assign to."""
        return [v for ty in Ty for v in self.of(ty, (VarKind.VAR, VarKind.FIELD))]

    def allows(self, ty: Ty) -> bool:
        """Whether an expression of type `ty` can be written here. An Address comes only from a
        variable, so it needs one in scope."""
        return ty != Ty.ADDRESS or bool(self.of(Ty.ADDRESS))

    def types(self) -> list[Ty]:
        """The types that an expression can have here."""
        return [ty for ty in Ty if self.allows(ty)]


class Param(NamedTuple):
    name: FeName
    ty: Ty
    # Whether a call passes it without its label.
    positional: bool

    def decl(self) -> str:
        return f"{'_ ' if self.positional else ''}{self.name}: {self.ty}"

    @property
    def var(self) -> Var:
        return Var(self.name, self.ty, VarKind.PARAM)


class Field(NamedTuple):
    """A field of a msg variant."""

    name: FeName
    ty: Ty

    def decl(self) -> str:
        return f"{self.name}: {self.ty}"


def decls(items: Iterable[Param | Field]) -> str:
    """The declarations of params or fields, as a list in Fe."""
    return ", ".join(item.decl() for item in items)


class Helper(NamedTuple):
    name: FeName
    params: list[Param]
    ret: Ty
    # Whether calling it runs a loop.
    heavy: bool


class Variant(NamedTuple):
    name: FeName
    selector: Selector
    fields: list[Field]
    ret: Ty | None


class Msg(NamedTuple):
    name: FeName
    variants: list[Variant]


class BodyKind(Enum):
    HELPER = "helper"
    INIT = "init"
    ARM = "arm"


class LoopKind(Enum):
    # The counter goes up at the end of the body.
    END = "end"
    # The counter goes up at the start of the body.
    START = "start"


@dataclass
class Body:
    """What the generator knows about the function body that it is writing."""

    kind: BodyKind
    ret: Ty | None
    # Statements left to write.
    budget: int
    # The storage fields that the body reads and writes.
    reads: set[FeName] = field(default_factory=set)
    writes: set[FeName] = field(default_factory=set)
    # The kind of each enclosing loop, innermost last.
    loops: list[LoopKind] = field(default_factory=list)
    # Whether it has a loop or calls a heavy helper.
    heavy: bool = False

    def may_fail(self) -> bool:
        """Whether the code here may fail."""
        return self.kind != BodyKind.INIT

    def may_return(self) -> bool:
        """Whether the body may return early."""
        return self.kind != BodyKind.INIT

    def may_loop(self) -> bool:
        """Whether a loop may start here."""
        if self.kind == BodyKind.HELPER:
            return len(self.loops) < MAX_HELPER_LOOP_DEPTH and not self.heavy
        return len(self.loops) < MAX_LOOP_DEPTH

    def may_continue(self) -> bool:
        """Whether `continue` may stand here."""
        return bool(self.loops) and self.loops[-1] == LoopKind.START

    def may_call(self, helper: Helper) -> bool:
        """Whether the code may call `helper` here."""
        return self.may_fail() and not (helper.heavy and self.loops)


class BodyWriter:
    """The writer of one function body. It holds the body and the scope at the point it writes."""

    def __init__(self, gen: "Gen", body: Body, sc: Iterable[Var]) -> None:
        self.gen, self.rng, self.body, self.sc = gen, gen.rng, body, Scope(sc)

    def write(self) -> list[FeLine]:
        """Returns the statements of the body, and its tail when it returns a value. It also
        records in the body the storage fields that the statements read and write, and whether
        they loop."""
        b = self.body
        lines: list[FeLine] = []
        while b.budget > 0:
            b.budget -= 1
            lines += self.stmt(0)
        if b.ret:
            tail = self.expr(b.ret, self.depth())
            lines.append(FeLine(tail.at(ATOM) if tail.may_read_as_record() else tail.text))
        return lines

    @contextmanager
    def inner(self, *extra: Var) -> Iterator[None]:
        """Puts the code of the `with` block in a new inner scope that also holds `extra`."""
        outer, self.sc = self.sc, Scope([*self.sc, *extra])
        try:
            yield
        finally:
            self.sc = outer

    # Expressions.

    def use(self, v: Var) -> E:
        if v.kind == VarKind.FIELD:
            self.body.reads.add(v.name)
        return E(v.name, ATOM)

    def callable(self, ty: Ty) -> list[Helper]:
        """The helpers returning `ty` that the body may call here."""
        return [h for h in self.gen.helpers if h.ret == ty and self.body.may_call(h)
                and all(self.sc.allows(p.ty) for p in h.params)]

    def call(self, h: Helper, d: int) -> E:
        args = []
        for p in h.params:
            a = self.expr(p.ty, d).text
            args.append(a if p.positional else f"{p.name}: {a}")
        if args and self.gen.chance(0.1):
            args[-1] += ","
        if h.heavy:
            self.body.heavy = True
        return E(f"{h.name}({', '.join(args)})", ATOM)

    def can_type(self) -> bool:
        """Whether a u256 expression with a type of its own can be written here."""
        return bool(self.sc.of(Ty.U256) or self.callable(Ty.U256))

    def typed_atom(self) -> E:
        vs = self.sc.of(Ty.U256)
        if vs and (not self.callable(Ty.U256) or self.gen.chance(0.8)):
            return self.use(self.rng.choice(vs))
        return self.call(self.rng.choice(self.callable(Ty.U256)), 0)

    def leaf(self, ty: Ty, typed: bool) -> E:
        g, vs = self.gen, self.sc.of(ty)
        if ty == Ty.U256:
            if typed:
                return self.typed_atom()
            if vs and g.chance(0.6):
                return self.use(self.rng.choice(vs))
            return E(g.literal(g.value()), ATOM, typed=False)
        if ty == Ty.BOOL:
            if vs and g.chance(0.6):
                return self.use(self.rng.choice(vs))
            return E(self.rng.choice(["true", "false"]), ATOM)
        return self.use(self.rng.choice(vs))

    def expr(self, ty: Ty, d: int, typed: bool = False) -> E:
        """An expression of type `ty` and depth at most `d`.

        With `typed`, a u256 expression has a type of its own (`E.typed`), which needs
        `can_type()`. An Address expression needs an Address in scope.
        """
        g = self.gen
        e = self.compound(ty, d, typed) if d > 0 and g.chance(0.7) else self.leaf(ty, typed)
        if e.prec > IF and e.prec < ATOM and g.chance(0.05):
            e = e.parenthesized()
        return e

    def compound(self, ty: Ty, d: int, typed: bool) -> E:
        rng, g = self.rng, self.gen
        forms = {"if": 2, "block": 1}
        if self.callable(ty):
            forms["call"] = 2
        if ty == Ty.U256:
            forms |= {"binary": 8, "not": 1}
        elif ty == Ty.BOOL:
            forms |= {"logic": 4, "not": 2, "eq": 2}
            if self.can_type():
                forms["cmp"] = 6
            if self.sc.allows(Ty.ADDRESS):
                forms["addr_eq"] = 1
        form = rng.choices(list(forms), weights=list(forms.values()))[0]
        if form == "call":
            return self.call(rng.choice(self.callable(ty)), d - 1)
        if form == "if":
            c = self.expr(Ty.BOOL, d - 1)
            first = rng.random() < 0.5
            x = self.expr(ty, d - 1, typed and first)
            y = self.expr(ty, d - 1, typed and not first)
            text = f"if {c.at(OR)} {{ {x.text} }} else {{ {y.text} }}"
            if g.chance(0.2):
                c2 = self.expr(Ty.BOOL, d - 1)
                z = self.expr(ty, d - 1)
                text = f"if {c.at(OR)} {{ {x.text} }} else if {c2.at(OR)} {{ {z.text} }} else {{ {y.text} }}"
            return E(text, IF, x.typed or y.typed)
        if form == "block":
            x = self.expr(ty, d - 1, typed)
            return E(f"{{ {x.text} }}", IF, x.typed)
        if form == "not":
            x = self.expr(ty, d - 1, typed)
            return E(("~" if ty == Ty.U256 else "!") + x.at(UNARY), UNARY, x.typed)
        if form == "binary":
            op = rng.choice(self.ops())
            first = rng.random() < 0.5
            x = self.expr(Ty.U256, d - 1, typed and first)
            y = self.operand(op, d - 1, typed and not first)
            return E(f"{x.at(op.prec)} {op.symbol} {y.at(op.prec + 1)}", op.prec, x.typed or y.typed)
        if form == "logic":
            symbol, p = rng.choice([("&&", AND), ("||", OR)])
            x, y = self.expr(Ty.BOOL, d - 1), self.expr(Ty.BOOL, d - 1)
            return E(f"{x.at(p)} {symbol} {y.at(p + 1)}", p)
        if form == "cmp":
            symbol = rng.choice(CMP_OPS)
            first = rng.random() < 0.5
            x = self.expr(Ty.U256, d - 1, first)
            y = self.expr(Ty.U256, d - 1, not first)
            left = x.parenthesized() if symbol == "<" and x.may_take_generics() else x
            return E(f"{left.at(CMP + 1)} {symbol} {y.at(CMP + 1)}", CMP)
        t = Ty.ADDRESS if form == "addr_eq" else Ty.BOOL
        x, y = self.expr(t, d - 1), self.expr(t, d - 1)
        return E(f"{x.at(CMP + 1)} {rng.choice(['==', '!='])} {y.at(CMP + 1)}", CMP)

    def ops(self) -> list[Op]:
        """The u256 operators that the body may use."""
        return [op for op in OPS if self.body.may_fail() or not op.fails]

    def operand(self, op: Op, d: int, typed: bool = False) -> E:
        """A right operand of `op`, of depth at most `d`."""
        if op.is_shift:
            return self.shift_amount(d, typed)
        return self.expr(Ty.U256, d, typed)

    def shift_amount(self, d: int, typed: bool) -> E:
        """A shift amount below 512, so that Fe's backend does not crash on it
        (docs/WORKAROUNDS.md). Amounts of 256 and more still occur."""
        g = self.gen
        if not typed and g.chance(0.6):
            return E(g.literal(self.rng.choice([0, 1, 8, 128, 255, 256, 300])), ATOM, False)
        e = self.expr(Ty.U256, d, typed)
        return E(f"{e.at(BITAND)} & {g.literal(SHIFT_MASK)}", BITAND, e.typed)

    def depth(self) -> int:
        return self.rng.choice([0, 1, 1, 2, 2, 3, 3, 4, 5])

    def cond(self) -> str:
        return self.expr(Ty.BOOL, self.depth()).at(OR)

    # Statements.

    def stmts(self, nest: int, n: int) -> list[FeLine]:
        """Up to `n` statements in a block that is `nest` blocks deep."""
        lines: list[FeLine] = []
        with self.inner():
            for _ in range(n):
                if self.body.budget <= 0:
                    break
                self.body.budget -= 1
                lines += self.stmt(nest)
        return lines

    def stmt(self, nest: int) -> list[FeLine]:
        """One statement. A declaration adds its local to the scope."""
        rng, g, b, sc = self.rng, self.gen, self.body, self.sc
        targets = sc.assignable()
        kinds = {"decl": 3}
        if targets:
            kinds["assign"] = 4
        if nest < 3:
            kinds["if"] = 2
            if b.may_loop():
                kinds["while"] = 1
        if b.may_fail():
            kinds["assert"] = 1
        if b.may_return():
            kinds["return"] = 1
        if b.loops:
            kinds["break"] = 1
        if b.may_continue():
            kinds["continue"] = 1
        kind = rng.choices(list(kinds), weights=list(kinds.values()))[0]
        if kind == "decl":
            ty = g.ty(sc)
            e = self.expr(ty, self.depth())
            v = Var(g.fresh("x"), ty, VarKind.VAR if g.chance(0.4) else VarKind.LET)
            decl = f"{v.kind} {v.name}"
            # A u256 without a type of its own needs the annotation (SPEC.md §2).
            if e.typed and g.chance(0.3):
                line = FeLine(f"{decl} = {e.text}")
            else:
                line = FeLine(f"{decl}: {ty} = {e.text}")
            sc.append(v)
            return [line]
        if kind == "assign":
            v = rng.choice(targets)
            if v.kind == VarKind.FIELD:
                b.writes.add(v.name)
            if v.ty == Ty.U256 and g.chance(0.5):
                op = rng.choice(self.ops())
                return [FeLine(f"{v.name} {op.symbol}= {self.operand(op, self.depth()).text}")]
            return [FeLine(f"{v.name} = {self.expr(v.ty, self.depth()).text}")]
        if kind == "if":
            out = [FeLine(f"if {self.cond()} {{")] + indent(self.stmts(nest + 1, rng.randint(0, 3)))
            while g.chance(0.3):
                out += ([FeLine(f"}} else if {self.cond()} {{")]
                        + indent(self.stmts(nest + 1, rng.randint(0, 2))))
            if g.chance(0.5):
                out += [FeLine("} else {")] + indent(self.stmts(nest + 1, rng.randint(0, 3)))
            return out + [FeLine("}")]
        if kind == "while":
            return self.loop(nest)
        if kind == "assert":
            c = self.expr(Ty.BOOL, self.depth()).text
            if g.chance(0.4):
                return [FeLine(f'assert!({c}, "{rng.choice(["no", "bad value", "x" * 31])}")')]
            return [FeLine(f"assert!({c})")]
        if kind == "return":
            value = f" {self.expr(b.ret, self.depth()).text}" if b.ret else ""
            return [FeLine(f"if {self.cond()} {{"), FeLine(f"    return{value}"), FeLine("}")]
        return [FeLine(f"if {self.cond()} {{"), FeLine(f"    {kind}"), FeLine("}")]

    def loop(self, nest: int) -> list[FeLine]:
        g, b = self.gen, self.body
        b.heavy = True
        i = Var(g.fresh("n"), Ty.U256, VarKind.COUNTER)
        k = g.literal(self.rng.randint(0, MAX_LOOP))
        form = self.rng.choice(list(LoopKind))
        b.loops.append(form)
        cond = f"{i.name} < {k}"
        with self.inner(i):
            if g.chance(0.3):
                cond += f" && {self.expr(Ty.BOOL, 2).at(AND + 1)}"
            body = self.stmts(nest + 1, self.rng.randint(1, 4))
        b.loops.pop()
        step = [FeLine(f"{i.name} += 1")]
        body = step + body if form == LoopKind.START else body + step
        head = [FeLine(f"var {i.name}: u256 = 0"), FeLine(f"while {cond} {{")]
        return head + indent(body) + [FeLine("}")]


class ContractWriter:
    """The writer of the contract and its msgs. It holds the contract's storage fields, and the
    selectors that its msg variants already use."""

    def __init__(self, gen: "Gen", fields: list[Var]) -> None:
        self.gen, self.rng, self.fields = gen, gen.rng, fields
        self.used = {PROBE_SELECTOR}

    def uses(self, body: Body) -> str:
        """The uses clause of `body`, with some unused entries."""
        g = self.gen
        entries: list[str] = []
        for f in self.fields:
            if f.name in body.writes or (f.name in body.reads and g.chance(0.1)):
                entries.append(f"mut {f.name}")
            elif f.name in body.reads or g.chance(0.15):
                entries.append(f.name)
        if not entries:
            return ""
        self.rng.shuffle(entries)
        return f" uses ({', '.join(entries)}{',' if g.chance(0.1) else ''})"

    def msgs(self) -> list[Msg]:
        """The msgs that the contract receives."""
        msgs = []
        for _ in range(self.rng.choice([1, 1, 1, 2])):
            variants = [self.variant() for _ in range(self.rng.randint(1, 6))]
            msgs.append(Msg(self.gen.fresh("M"), variants))
        return msgs

    def variant(self) -> Variant:
        """A msg variant with a selector that no other variant uses."""
        rng = self.rng
        sel = Selector(rng.choice([rng.randrange(1, 64), rng.getrandbits(32)]))
        while sel in self.used:
            sel = Selector(rng.getrandbits(32))
        self.used.add(sel)
        vfields = [Field(FeName(f"a{j}"), rng.choice(list(Ty)))
                   for j in range(rng.choice([0, 1, 1, 2, 3]))]
        sc = Scope([*self.fields, *(Var(f.name, f.ty, VarKind.PARAM) for f in vfields)])
        return Variant(self.gen.fresh("V"), sel, vfields, rng.choice([None, *sc.types()]))

    def contract(self, init_params: list[Param] | None, msgs: list[Msg]) -> list[FeLine]:
        """The contract, with an init that takes `init_params` unless they are None."""
        g = self.gen
        lines = indent([FeLine(f"mut {f.name}: {f.ty},") for f in self.fields])
        if init_params is not None:
            body = Body(BodyKind.INIT, None, self.rng.randint(0, 4))
            sc = [*g.consts, *self.fields, *(p.var for p in init_params)]
            code = BodyWriter(g, body, sc).write()
            head = FeLine(f"init({decls(init_params)}){self.uses(body)} {{")
            lines += [FeLine("")] + indent([head] + indent(code) + [FeLine("}")])
        for m in msgs:
            arms = [line for v in m.variants for line in self.arm(v)]
            recv = [FeLine(f"recv {m.name} {{")] + indent(arms) + [FeLine("}")]
            lines += [FeLine("")] + indent(recv)
        return [FeLine("contract C {")] + lines + [FeLine("}")]

    def arm(self, v: Variant) -> list[FeLine]:
        """The recv arm of the variant `v`."""
        g = self.gen
        binds: list[str] = []
        locals_: list[Var] = []
        for f in v.fields:
            local = f.name if g.chance(0.5) else g.fresh("b")
            binds.append(f.name if local == f.name else f"{f.name}: {local}")
            locals_.append(Var(local, f.ty, VarKind.PARAM))
        body = Body(BodyKind.ARM, v.ret, self.rng.randint(0, 7))
        lines = BodyWriter(g, body, [*g.consts, *self.fields, *locals_]).write()
        ret = f" -> {v.ret}" if v.ret else ""
        head = f"{v.name} {{ {', '.join(binds)} }}" if binds else f"{v.name} {{}}"
        return [FeLine(f"{head}{ret}{self.uses(body)} {{")] + indent(lines) + [FeLine("}")]


class Generated(NamedTuple):
    """A generated program and its call script."""

    program: FeSource
    calls: str


class Gen:
    """The generator of one program."""

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.count = 0
        self.consts = Scope()
        # The u256 ones of `consts`, with their values.
        self.u256_consts: list[Const] = []
        self.helpers: list[Helper] = []

    def fresh(self, prefix: str) -> FeName:
        self.count += 1
        name = FeName(f"{prefix}{self.count}")
        # Fe0 rejects a name such as i32 because it is a type name (SPEC.md §1).
        assert not re.fullmatch(r"[iu][0-9]+", name), name
        return name

    def chance(self, p: float) -> bool:
        return self.rng.random() < p

    # Values and literals.

    def value(self) -> Word:
        """A u256 value, biased towards small and edge values."""
        r = self.rng.random()
        if r < 0.5:
            return Word(self.rng.randrange(11))
        if r < 0.8:
            return Word(self.rng.choice(EDGES))
        return Word(self.rng.getrandbits(self.rng.choice([8, 64, 160, 256])))

    def literal(self, v: int) -> str:
        """`v` as an integer literal, in one of the forms of SPEC.md §1."""
        if v >= 2**64 or self.chance(0.15):
            digits = f"{v:x}" if self.chance(0.7) else f"{v:X}"
            return self.rng.choice(["0x", "0X"]) + digits
        if v >= 1000 and self.chance(0.3):
            return f"{v:_}"
        return str(v)

    def ty(self, sc: Scope) -> Ty:
        """A type that an expression in `sc` can have."""
        return self.rng.choice(sc.types())

    # Items.

    def constant(self) -> FeLine:
        """Declares a new constant, which later code may use, and returns its declaration line."""
        ty = Ty.BOOL if self.consts and self.chance(0.25) else Ty.U256
        name = self.fresh("K")
        if ty == Ty.BOOL:
            k = self.rng.choice(self.u256_consts)
            op = self.rng.choice(CMP_OPS)
            text = f"{k.name} {op} {self.literal(self.value())}"
        else:
            c = self.const_expr(self.rng.randint(0, 3))
            text = c.expr.text
            self.u256_consts.append(Const(name, c.value))
        self.consts.append(Var(name, ty, VarKind.CONST))
        return FeLine(f"const {name}: {ty} = {text}")

    def const_expr(self, d: int) -> ConstExpr:
        """A u256 expression of literals and earlier constants that does not fail."""
        rng = self.rng
        if d == 0 or self.chance(0.3):
            if self.u256_consts and self.chance(0.4):
                k = rng.choice(self.u256_consts)
                return ConstExpr(E(k.name, ATOM), k.value)
            v = self.value()
            return ConstExpr(E(self.literal(v), ATOM), v)
        ops: list[Op | str] = [*OPS, "~"]
        for _ in range(10):
            op = rng.choice(ops)
            if isinstance(op, str):
                x = self.const_expr(d - 1)
                return ConstExpr(E("~" + x.expr.at(UNARY), UNARY), Word(MAX ^ x.value))
            x, y = self.const_expr(d - 1), self.const_expr(d - 1)
            folded = op.evaluate(x.value, y.value)
            if folded is not None:
                text = f"{x.expr.at(op.prec)} {op.symbol} {y.expr.at(op.prec + 1)}"
                return ConstExpr(E(text, op.prec), Word(folded))
        return ConstExpr(E("1", ATOM), Word(1))

    def helper(self) -> list[FeLine]:
        rng = self.rng
        name = self.fresh("h")
        params = [Param(self.fresh("p"), rng.choice(list(Ty)), self.chance(0.5))
                  for _ in range(rng.randint(0, 3))]
        sc = Scope([*self.consts, *(p.var for p in params)])
        ret = self.ty(sc)
        body = Body(BodyKind.HELPER, ret, rng.randint(0, 5))
        lines = BodyWriter(self, body, sc).write()
        self.helpers.append(Helper(name, params, ret, body.heavy))
        return [FeLine(f"fn {name}({decls(params)}) -> {ret} {{")] + indent(lines) + [FeLine("}")]

    def msg_item(self, m: Msg) -> list[FeLine]:
        out = [FeLine(f"msg {m.name} {{")]
        for v in m.variants:
            sel = f"{v.selector:#x}" if self.chance(0.7) else str(v.selector)
            fs = f" {{ {decls(v.fields)} }}" if v.fields else ""
            ret = f" -> {v.ret}" if v.ret else ""
            out += indent([FeLine(f"#[selector = {sel}]"), FeLine(f"{v.name}{fs}{ret},")])
        return out + [FeLine("}")]

    def order(self, consts: list[list[FeLine]], others: list[list[FeLine]]) -> list[list[FeLine]]:
        """The items in a random order. Items may come in any order, except that a constant
        refers only to earlier ones, so `consts` keep their order."""
        self.rng.shuffle(others)
        items: list[list[FeLine]] = []
        for item in others:
            if consts and self.chance(0.5):
                items.append(consts.pop(0))
            items.append(item)
        return items + consts

    def program(self) -> Generated:
        """Returns the program and its call script."""
        rng = self.rng
        consts = [[self.constant()] for _ in range(rng.choice([0, 0, 1, 2, 3]))]
        helpers = [self.helper() for _ in range(rng.choice([0, 1, 1, 2, 3]))]
        fields = [Var(self.fresh("s"), rng.choice(list(Ty)), VarKind.FIELD)
                  for _ in range(rng.randint(1, 4))]
        writer = ContractWriter(self, fields)
        msgs = writer.msgs()
        init_params = [Param(self.fresh("p"), rng.choice(list(Ty)), False)
                       for _ in range(rng.randint(0, 3))] if self.chance(0.8) else None
        contract = writer.contract(init_params, msgs)
        items = self.order(consts, helpers + [self.msg_item(m) for m in msgs] + [contract])
        text = FeSource(f"// Generated by tools/gen.py with seed {self.seed}.\n"
                        + "\n\n".join("\n".join(item) for item in items) + "\n")
        return Generated(text, self.calls(init_params or [], [v for m in msgs for v in m.variants]))

    # Call scripts.

    def word(self, ty: Ty) -> Word:
        if ty == Ty.U256:
            return self.value()
        if ty == Ty.BOOL:
            return Word(self.rng.randrange(2))
        return Word(self.rng.choice([0, 0xb1, 0xcc, self.rng.getrandbits(160), (1 << 160) - 1]))

    def args(self, types: list[Ty]) -> Args:
        """Argument words for `types`, sometimes malformed, and options."""
        words = [self.word(t) for t in types]
        value = Wei(0)
        extra = 0
        r = self.rng.random()
        if r < 0.08 and words:
            words.pop()
        elif r < 0.16 and Ty.BOOL in types:
            words[types.index(Ty.BOOL)] = Word(self.rng.choice([2, MAX]))
        elif r < 0.24 and Ty.ADDRESS in types:
            i = types.index(Ty.ADDRESS)
            words[i] = Word(words[i] | 1 << self.rng.choice([160, 255]))
        elif r < 0.3:
            value = Wei(self.rng.choice([1, 7]))
        if self.chance(0.1):
            extra = self.rng.randint(1, 40)
        return Args(tuple(words), value, extra)

    def calls(self, init_params: list[Param], variants: list[Variant]) -> str:
        types = [p.ty for p in init_params]
        lines: list[ScriptLine] = [InitLine(Args(tuple(self.word(t) for t in types)))]
        for _ in range(self.rng.choice([0, 1, 2])):
            lines.append(DeployLine(self.args(types)))
        for _ in range(self.rng.randint(5, 20)):
            v = self.rng.choice(variants)
            lines.append(NamedCallLine(v.name, self.args([f.ty for f in v.fields])))
        return "".join(line.render() + "\n" for line in lines)


def write(seed: int) -> Path:
    """Writes the program of `seed` and its call script to GEN, and returns the program's path."""
    generated = Gen(seed).program()
    path = GEN / f"s{seed}.fe"
    path.write_text(generated.program)
    embed.calls_path(path).write_text(generated.calls)
    return path


def main() -> None:
    ap = embed.parser(__doc__)
    ap.add_argument("--seed", type=int, default=1, help="the first seed (default 1)")
    ap.add_argument("-n", type=int, default=25, help="the number of programs (default 25)")
    args = ap.parse_args()
    shutil.rmtree(GEN, ignore_errors=True)
    GEN.mkdir(parents=True)
    paths = [write(s) for s in range(args.seed, args.seed + args.n)]
    programs = [embed.Program.load(p) for p in paths]
    embed.Corpus(programs, []).harness(OUT, embed.requested_fe_test(args))


if __name__ == "__main__":
    main()
