"""Shared parts of the scripts that write Fe tests.

The differential tests that these scripts write call fe0/src/difftest.fe, and every generator
writes them through this module, so that all of them call it the same way.
"""
import bisect
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, fields
from functools import cache
from pathlib import Path
from typing import ClassVar, NamedTuple, NewType, Self

from eth_abi.abi import decode as abi_decode
from eth_abi.abi import encode as abi_encode
from eth_utils.crypto import keccak

# The text of a Fe program or module.
FeSource = NewType("FeSource", str)
# One line of Fe code, without its line end.
FeLine = NewType("FeLine", str)
# A Fe expression, such as a string literal or a `difftest::CompileError`.
FeExpr = NewType("FeExpr", str)
# A piece of Fe code that is neither a line nor an expression, such as a type, the statements of
# a block, or what follows the name of a msg variant.
FeCode = NewType("FeCode", str)
# A Fe identifier that names a contract, a struct, a function or a local.
FeName = NewType("FeName", str)
# The name of a Fe test function, as `fe test` reports it.
TestName = NewType("TestName", str)
# A call of a `difftest::Payload` method that appends bytes, without its receiver, such as
# `push(0x99)`.
Push = NewType("Push", str)
# An amount of wei.
Wei = NewType("Wei", int)
# A 256-bit ABI word.
Word = NewType("Word", int)
# The index of a node account among the node's funded accounts.
AccountIndex = NewType("AccountIndex", int)
# A number of EXTRA_BYTE bytes that a deployment or call appends after its ABI words.
ExtraBytes = NewType("ExtraBytes", int)
# The code of a Panic, with which Fe's own checks fail a test.
PanicCode = NewType("PanicCode", int)
# The Panic code of an arithmetic overflow (docs/SPEC.md §4).
OVERFLOW = PanicCode(0x11)
# A failed test's error names its case by this number (DESIGN.md §10). A call script numbers a
# case by its line, and the codegen tests number theirs around MAIN_CASE.
CaseNumber = NewType("CaseNumber", int)
# The main deployment of a call script without an `init` line, which no line names (the
# call-script format in the docstring of tools/embed.py).
NO_LINE = CaseNumber(0)


def script_place(number: CaseNumber) -> str:
    """Returns the place of the case `number` in its call script, which a failure's report names
    (DESIGN.md §10)."""
    return "main deployment (no init line)" if number == NO_LINE else f"line {number}"


@dataclass(frozen=True)
class Account:
    """The address of a node account, as an argument of a deployment or call.

    On a node, it is the address of the account at `index`, which a `from` of the same index
    sends from. Under `fe test`, it is the address of the test contract for every index.
    DESIGN.md §10, "On a node", says why.
    """

    index: AccountIndex


# The name of a deployment in a call script, as in `@t0`. THIS names the main deployment.
DeploymentName = NewType("DeploymentName", str)
# The form of a DeploymentName: a lowercase identifier.
DEPLOYMENT_NAME = r"[a-z][a-z0-9_]*"
# The name of the program's own main deployment, which no other deployment may take.
THIS: DeploymentName = DeploymentName("this")


@dataclass(frozen=True)
class Named:
    """The address of a deployment that the call script named, as an argument such as `@t0`.

    Only a node resolves it (tools/node.py), to the address that the same build's deployment
    created.
    """

    # The start of the token, before the name.
    SIGIL: ClassVar[str] = "@"

    name: DeploymentName

    @classmethod
    def parse(cls, token: str) -> Self | None:
        """Returns the deployment that `token` names, or None when `token` is no `@name`."""
        m = re.fullmatch(rf"{re.escape(cls.SIGIL)}({DEPLOYMENT_NAME})", token)
        return cls(DeploymentName(m[1])) if m else None

    def __str__(self) -> str:
        """Returns the token, such as `@t0`."""
        return f"{self.SIGIL}{self.name}"


# An argument that names an address. The place that sends it resolves it (AddressWord).
AddressArg = Account | Named
# An argument of a deployment or call, which takes one ABI word.
Arg = Word | AddressArg
# The address that an AddressArg names, as an ABI word.
AddressWord = Callable[[AddressArg], Word]


class Selector(int):
    """The 4-byte selector of a msg variant. Errors when the value does not fit in 4 bytes."""

    def __new__(cls, value: int) -> Self:
        if not 0 <= value < 1 << 32:
            raise ValueError(f"selector {value:#x} does not fit in 4 bytes")
        return super().__new__(cls, value)


# A byte offset into a FeSource.
ByteOffset = NewType("ByteOffset", int)
# The letter of a phase of Fe0, such as "E" for effects.
PhaseLetter = NewType("PhaseLetter", str)
# A release of Fe, such as `26.7.0`.
FeVersion = NewType("FeVersion", str)
# The version of an ingot, as its fe.toml holds it, such as "0.1.0".
Version = NewType("Version", str)


def find_fe() -> str:
    """Returns the path of the fe binary. The environment variable FE sets it, and the `fe` on
    PATH is the default. Exits with a message when there is neither."""
    fe = os.environ.get("FE") or shutil.which("fe")
    if fe is None:
        sys.exit("no fe on PATH: install Fe, or set FE to the path of the fe binary")
    return fe


FE: str = find_fe()
ROOT: Path = Path(__file__).resolve().parent.parent
FE0: Path = ROOT / "fe0"
MAX: Word = Word((1 << 256) - 1)


def _fe_const(path: Path, name: str, type_: str, value: str) -> str:
    """Returns the first group that the pattern `value` matches in the declaration of the constant
    `name` in the Fe module `path`. `type_` is a pattern that matches the constant's type. Errors
    with ValueError when the module has no such declaration."""
    m = re.search(rf"^(?:pub )?const {name}: {type_} = {value}$", path.read_text(), re.MULTILINE)
    if m is None:
        raise ValueError(f"{path} declares no const {name}: {type_}")
    return m[1]


def fe_const(path: Path, name: str) -> int:
    """Returns the value of the `usize` constant `name` that the Fe module `path` declares. Errors
    as `_fe_const` does."""
    return int(_fe_const(path, name, "usize", r"(\d+)"))


def fe_string(path: Path, name: str) -> str:
    """Returns the value of the `String` constant `name` that the Fe module `path` declares. The
    value holds no quote and no backslash. Errors as `_fe_const` does."""
    return _fe_const(path, name, r"String<\d+>", r'"([^"\\]*)"')


def fe_build(ingot: Path, out_dir: Path, *options: str) -> None:
    """Builds the ingot `ingot` into `out_dir` with `fe build` and `options`. Exits with what
    `fe build` printed when it fails."""
    r = subprocess.run([FE, "build", *options, "--out-dir", str(out_dir), str(ingot)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Errors when building {ingot.relative_to(ROOT)}:\n{r.stdout}{r.stderr}")


# The first line of `fe --version`, such as `fe 26.7.0 (e6e6342b2)`.
_FE_VERSION: re.Pattern[str] = re.compile(r"fe (?P<version>\S+) ")


def fe_version() -> FeVersion:
    """Returns the release of the fe binary. Errors with RuntimeError when `fe --version`
    prints no release."""
    out = subprocess.run([FE, "--version"], check=True, capture_output=True, text=True).stdout
    m = _FE_VERSION.match(out)
    if m is None:
        raise RuntimeError(f"{FE} --version prints no release: {out.strip()}")
    return FeVersion(m["version"])


def ingot_version(manifest: Path) -> Version:
    """Returns the version that the ingot file `manifest` holds."""
    return Version(tomllib.loads(manifest.read_text())["ingot"]["version"])


def poll[T](check: Callable[[], T | None], timeout: float, interval: float) -> T:
    """Calls `check` every `interval` seconds until it returns a value other than None, and
    returns that value. Errors with TimeoutError when `timeout` seconds pass first, or as
    `check` does."""
    deadline = time.monotonic() + timeout
    while (got := check()) is None:
        if time.monotonic() > deadline:
            raise TimeoutError(f"no result within {timeout} s")
        time.sleep(interval)
    return got


# The deepest nesting of blocks and binary expressions that Fe0's parser accepts.
MAX_DEPTH: int = fe_const(FE0 / "src/parser.fe", "MAX_DEPTH")
# Longer than MAX_DEPTH, so a chain of this many `else if` shows that the parser and the code
# generator read such a chain in a loop, not by recursion.
CHAIN_LEN = 40
assert CHAIN_LEN > MAX_DEPTH


def source(lines: Iterable[FeLine]) -> FeSource:
    """Returns the text of `lines`, with a line end after each."""
    return FeSource("".join(s + "\n" for s in lines))


def lines(text: FeSource) -> list[FeLine]:
    """Returns the lines of `text`, split at each `\n`. A `text` that ends with `\n` gives an
    empty last line, so `source(lines(text))` is `text` with one more `\n`."""
    return [FeLine(s) for s in text.split("\n")]


def lit(s: str) -> FeExpr:
    """`s` as a Fe string literal."""
    return FeExpr('"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"')


def write_formatted(path: Path, text: FeSource) -> None:
    """Writes `text` to `path` and formats the file with `fe fmt`. Errors when `text` is not
    valid Fe, or when `fe fmt` fails."""
    path.write_text(text)
    result = subprocess.run([FE, "fmt", str(path)], check=True, capture_output=True, text=True)
    # `fe fmt` exits with 0 on a file that does not parse, and only warns on stderr.
    if result.stderr:
        raise RuntimeError(f"fe fmt {path}: {result.stderr.strip()}")


class Payload(ABC):
    """Bytes sent to a contract, together with a value in wei. It mirrors `difftest::Payload` in
    fe0/src/difftest.fe."""

    # The arguments that take one ABI word each.
    words: Sequence[Arg] = ()

    def __init__(self, value: Wei) -> None:
        self.value = value

    @abstractmethod
    def pushes(self) -> list[Push]:
        """Returns the method calls that append the bytes."""

    @abstractmethod
    def encode(self, address: AddressWord) -> bytes:
        """Returns the bytes, as the pushes append them, with `address` giving each
        AddressArg."""

    @property
    def named(self) -> list[DeploymentName]:
        return [a.name for a in self.words if isinstance(a, Named)]

    def build(self, var: FeName) -> list[FeLine]:
        """Returns the Fe statements that declare `var` as a `difftest::Payload` and fill it with
        the bytes."""
        wei = f"std::evm::wei({self.value})" if self.value else "Wei::zero()"
        new = FeLine(f"var {var} = difftest::Payload::new({wei})")
        return [new] + [FeLine(f"{var}.{c}") for c in self.pushes()]


# The byte that `extra` appends after the words.
EXTRA_BYTE: int = 0x99


def push_arg(a: Arg) -> Push:
    """Returns the Payload method call that appends the argument `a` as one ABI word. Errors with
    ValueError when `a` is Named."""
    if isinstance(a, Named):
        raise ValueError(f"{a} names a deployment, which only a node makes")
    return Push("push_sender()") if isinstance(a, Account) else Push(f"push_word({a:#x})")


def push_words(words: Sequence[Arg], extra: ExtraBytes) -> list[Push]:
    """Returns the Payload method calls that append the ABI `words`, then `extra` bytes of
    EXTRA_BYTE."""
    return [*map(push_arg, words)] + [Push(f"push({EXTRA_BYTE:#x})")] * extra


def encode_words(words: Sequence[Arg], extra: ExtraBytes, address: AddressWord) -> bytes:
    """Returns the ABI `words`, then `extra` bytes of EXTRA_BYTE, as push_words appends them.
    `address` gives the word of each AddressArg."""
    resolved = (address(a) if isinstance(a, AddressArg) else a for a in words)
    return b"".join(w.to_bytes(32, "big") for w in resolved) + bytes([EXTRA_BYTE]) * extra


class Deploy(Payload):
    """Constructor arguments: words, then `extra` bytes."""

    def __init__(self, *words: Arg, extra: ExtraBytes = ExtraBytes(0),
                 value: Wei = Wei(0)) -> None:
        super().__init__(value)
        self.words, self.extra = words, extra

    def pushes(self) -> list[Push]:
        return push_words(self.words, self.extra)

    def encode(self, address: AddressWord) -> bytes:
        return encode_words(self.words, self.extra, address)


class Call(Payload):
    """Calldata: a 4-byte selector, words, then `extra` bytes."""

    def __init__(self, sel: Selector, *words: Arg, extra: ExtraBytes = ExtraBytes(0),
                 value: Wei = Wei(0)) -> None:
        super().__init__(value)
        self.sel, self.words, self.extra = sel, words, extra

    def pushes(self) -> list[Push]:
        return [Push(f"push_selector({self.sel:#x})")] + push_words(self.words, self.extra)

    def encode(self, address: AddressWord) -> bytes:
        return self.sel.to_bytes(4, "big") + encode_words(self.words, self.extra, address)


class RawCall(Payload):
    """Calldata given byte by byte."""

    def __init__(self, *data: int, value: Wei = Wei(0)) -> None:
        super().__init__(value)
        self.data = data

    def pushes(self) -> list[Push]:
        return [Push(f"push({b})") for b in self.data]

    def encode(self, address: AddressWord) -> bytes:
        return bytes(self.data)


# A failed test's error names the dispatcher probe by this index (DESIGN.md §10).
ProbeIndex = NewType("ProbeIndex", int)


@dataclass(frozen=True)
class Probe:
    """A call that only the dispatcher answers. Fe0's dispatcher must revert with empty data where
    Fe's does, so every program's test sends these calls (ADR 0002; SPEC.md §6, dispatcher steps
    1 and 3)."""

    index: ProbeIndex
    payload: Payload

    @property
    def arg(self) -> FeCode:
        return FeCode(f"index: {self.index}")


# A selector that DISPATCH sends as an unknown one.
PROBE_SELECTOR: Selector = Selector(0x7777)
# Calls that reach the dispatcher's empty reverts: no selector, a short one, and an unknown one.
DISPATCH: list[Probe] = [Probe(ProbeIndex(k), p) for k, p in
                         enumerate([RawCall(), RawCall(0, 0, 1), Call(PROBE_SELECTOR)], start=1)]


def difftest_use(ingot: str) -> FeLine:
    """Returns the line that imports the difftest module.

    `ingot` is the name under which the importing code knows the fe0 ingot.
    """
    return FeLine(f"use {ingot}::difftest")


# A byte offset into the code of a contract.
CodeOffset = NewType("CodeOffset", int)
# The modules whose `#[error]` structs a failed differential test reverts with.
ERROR_MODULES: tuple[Path, ...] = (FE0 / "src/diag.fe", FE0 / "src/difftest.fe")
# The declaration of an error in ERROR_MODULES, which captures its name and its fields.
_ERROR_DECL: re.Pattern[str] = re.compile(r"^#\[error\]\npub struct (\w+) \{([^}]*)\}$", re.M)
# A field of an error in ERROR_MODULES. Each field is one ABI word.
_ERROR_FIELD: re.Pattern[str] = re.compile(r"\s*pub (\w+): u256\s*")
# The selector of a Panic, as Fe's own checks revert with it.
PANIC_SELECTOR: bytes = keccak(text="Panic(uint256)")[:4]


class ErrorDecl(NamedTuple):
    """An error that ERROR_MODULES declare."""

    name: FeName
    fields: tuple[FeName, ...]

    @classmethod
    def all(cls) -> list[Self]:
        """Returns the errors that ERROR_MODULES declare, in order. Errors with ValueError when a
        field is not a u256."""
        decls = []
        for module in ERROR_MODULES:
            for name, body in _ERROR_DECL.findall(module.read_text()):
                matches = [_ERROR_FIELD.fullmatch(f) for f in body.split(",") if f.strip()]
                if not all(matches):
                    raise ValueError(f"{module}: a field of {name} is not `pub <name>: u256`")
                decls.append(cls(FeName(name), tuple(FeName(m[1]) for m in matches if m)))
        return decls

    @property
    def selector(self) -> bytes:
        """Returns the error's selector, as Solidity and Fe compute it."""
        return keccak(text=f"{self.name}({','.join(['uint256'] * len(self.fields))})")[:4]


@dataclass(frozen=True)
class Failure:
    """What a failed differential test reports through its revert data, which says what failed
    and where (DESIGN.md §10). Each subclass but Panicked mirrors an error of ERROR_MODULES with
    its name and fields, which `check_errors` checks."""

    @classmethod
    def of_words(cls, words: Sequence[int]) -> Failure:
        """Returns the failure of this class whose fields, in order, are `words`."""
        return cls(*words)

    @staticmethod
    def decode(revert: bytes) -> Failure | None:
        """Returns the failure that the revert data `revert` names, or None when it names none.
        Errors with eth_abi's DecodingError when the data is shorter than the error's fields, and
        as `of_words` does."""
        if revert[:4] == PANIC_SELECTOR:
            return Panicked(PanicCode(int.from_bytes(revert[4:])))
        decl = _errors_by_selector().get(revert[:4])
        if decl is None:
            return None
        words: tuple[int, ...] = abi_decode(["uint256"] * len(decl.fields), revert[4:])
        return _failure_classes()[decl.name].of_words(words)


@cache
def _errors_by_selector() -> dict[bytes, ErrorDecl]:
    """Returns the errors of ERROR_MODULES, by selector."""
    return {d.selector: d for d in ErrorDecl.all()}


def _failure_classes() -> dict[str, type[Failure]]:
    """Returns the subclasses of Failure, by name."""
    return {c.__name__: c for c in Failure.__subclasses__()}


@dataclass(frozen=True)
class Panicked(Failure):
    code: PanicCode


@dataclass(frozen=True)
class CaseDiffers(Failure):
    """The builds broke the subset rule on this case. Either one deployment created a contract and
    the other did not, or the success flags or the return data differ (SPEC.md §8)."""

    number: CaseNumber


@dataclass(frozen=True)
class ProbeDiffers(Failure):
    index: ProbeIndex


@dataclass(frozen=True)
class TooLarge(Failure):
    """Fe0's build exceeds the EIP-170 or EIP-3860 limit. The test EVM does not enforce these
    limits, so the harness checks them itself (DESIGN.md §8a, §10)."""

    number: CaseNumber


@dataclass(frozen=True)
class Accepted(Failure):
    """Fe0 accepted a program that must fail with the error its header names (SPEC.md §8,
    "Rejected programs")."""


@dataclass(frozen=True)
class CodeDiffers(Failure):
    """The native CLI and Fe0 on the EVM gave different code for one program. The two targets share
    one library, so they must agree byte for byte (DESIGN.md §1, §10, "The native CLI")."""

    # The first byte that differs.
    offset: CodeOffset


@dataclass(frozen=True)
class CompileError(Failure):
    """Fe0 rejected the program, or rejected it with another error or position than the reject
    header names (SPEC.md §8)."""

    code: DiagCode
    offset: ByteOffset

    @classmethod
    def of_words(cls, words: Sequence[int]) -> Failure:
        """Returns the failure whose words are the value of the code (`DiagCode.value`) and the
        offset. Errors as `DiagCode.of_value` does."""
        value, offset = words
        return cls(DiagCode.of_value(value), ByteOffset(offset))

    @property
    def diag(self) -> Diag:
        return Diag(self.code, self.offset)


def check_errors() -> None:
    """Checks that each error of ERROR_MODULES has the name and the fields of a Failure subclass, and
    each Failure subclass but Panicked has an error."""
    decls = {d.name: d.fields for d in ErrorDecl.all()}
    classes = {name: tuple(f.name for f in fields(c))
               for name, c in _failure_classes().items() if c is not Panicked}
    assert decls == classes, f"{ERROR_MODULES} declare {decls}, but fegen.Failure has {classes}"


class Case(NamedTuple):
    """One deployment or call on which both builds must agree (SPEC.md §8). Its number is what a
    failure reports (DESIGN.md §10)."""

    number: CaseNumber
    payload: Payload
    # The account that sends the case. It applies only on a node (tools/node.py), as DESIGN.md
    # §10, "On a node", says.
    sender: AccountIndex = AccountIndex(0)

    @property
    def arg(self) -> FeCode:
        return FeCode(f"case: {self.number}")


class CallCase(NamedTuple):
    """A call may go to another deployment of the script, but only on a node. A test inside
    `fe test` cannot deploy another program (DESIGN.md §10, "On a node"; ADR 0020)."""

    case: Case
    to: DeploymentName = THIS

    @property
    def node_only(self) -> bool:
        return self.to != THIS or bool(self.case.payload.named)


class Callee(NamedTuple):
    """A deployment of another program, which the program under test may call."""

    name: DeploymentName
    # The program, a .fe file beside the program under test.
    program: Path
    # Its constructor arguments, value and sender.
    case: Case


class Cases(NamedTuple):
    """What a differential test sends. Every test also sends the calls of DISPATCH."""

    # The deployment that gets the calls. It must create a contract.
    main: Case
    # Other deployments, checked only for whether they create a contract.
    deploys: Sequence[Case]
    # The calls, in script order, before those of DISPATCH.
    calls: Sequence[CallCase]
    # The deployments of other programs, made first, in order.
    callees: Sequence[Callee] = ()

    @property
    def node_only(self) -> bool:
        """A test inside `fe test` can neither deploy another program nor resolve a deployment's
        address, so only a node runs such a test (DESIGN.md §10, "On a node")."""
        return (bool(self.callees) or any(d.payload.named for d in [self.main, *self.deploys])
                or any(c.node_only for c in self.calls))


# The wei that the test of one program spends at most on its deployments and calls.
BALANCE: Wei = Wei(1000)
# The effects of a function that deploys and calls contracts.
USES_EVM = "uses (evm: mut Evm)"


def indent(lines: list[FeLine]) -> list[FeLine]:
    """Returns `lines` indented by one level of Fe code."""
    return [FeLine("    " + s) for s in lines]


def evm_test(name: TestName, balance: Wei, statements: list[FeLine]) -> list[FeLine]:
    """Returns the lines of a test function `name` that runs `statements`, with `balance` wei to
    spend on the EVM."""
    head = [FeLine(f"#[test(balance = {balance})]"), FeLine(f"fn {name}() {USES_EVM} {{")]
    return head + indent(statements) + [FeLine("}")]


@dataclass(frozen=True)
class DiffTest:
    """A test that compares Fe0's build of a program with the official build.

    The test fails with the error (`Failure`) of the first case whose builds differ.
    """

    # The test function's name.
    test: TestName
    # The official build's contract, declared in the test's module.
    contract: FeName
    # The program as Fe0 compiles it.
    source: FeSource
    # The deployments and calls that the test sends.
    cases: Cases

    @property
    def runner(self) -> FeName:
        """Returns the name of the function that sends the cases."""
        return FeName(f"run_{self.test}")

    def lines(self) -> list[FeLine]:
        """Returns the lines of the runner and of the test function. The runner sends every call
        to the main deployment. Errors with ValueError when only a node can run the test
        (Cases.node_only)."""
        if self.cases.node_only:
            raise ValueError(f"only a node can run the test {self.test}")
        theirs = (f"difftest::theirs({self.contract}::init_code_offset(),"
                  f" {self.contract}::init_code_len())")
        ours = f"difftest::ours({lit(self.source)})"
        out = [FeLine(""), FeLine(f"pub fn {self.runner}() {USES_EVM} {{"),
               FeLine(f"    let b = difftest::Builds {{ ours: {ours}, theirs: {theirs} }}")]
        a = FeName("a")
        for d in self.cases.deploys:
            out += block(d.payload.build(a) + [FeLine(f"let _ = b.deploy({a}, {d.arg})")])
        main = self.cases.main
        out += indent(main.payload.build(a))
        out.append(FeLine(f"    let p = b.deploy_main({a}, {main.arg})"))
        for c in self.cases.calls:
            out += call(FeName("call"), c.case)
        for probe in DISPATCH:
            out += call(FeName("probe"), probe)
        test = evm_test(self.test, BALANCE, [FeLine(f"{self.runner}()")])
        return out + [FeLine("}"), FeLine("")] + test


def call(method: FeName, sent: Case | Probe) -> list[FeLine]:
    """Returns the block of a runner that sends `sent` to the main deployment with the
    `difftest::Deployed` method `method`."""
    d = FeName("d")
    return block(sent.payload.build(d) + [FeLine(f"p.{method}({d}, {sent.arg})")])


def reject_test(test: TestName, source: FeSource, expected: "Diag") -> list[FeLine]:
    """Returns the lines of a test function that checks that Fe0 rejects `source` with the
    error `expected`."""
    check = f"difftest::rejects({lit(source)}, {expected.rejected()})"
    return [FeLine(""), FeLine("#[test]"), FeLine(f"fn {test}() {{"), FeLine(f"    {check}"),
            FeLine("}")]


def block(statements: list[FeLine]) -> list[FeLine]:
    """Returns `statements` as a braced block inside a runner."""
    return indent([FeLine("{")] + indent(statements) + [FeLine("}")])


# What ends a line, as fe0's Text.line_col counts lines: `\n`, `\r\n` or a lone `\r`.
LINE_END = r"\r\n?|\n"


def line_starts(data: bytes) -> list[ByteOffset]:
    """Returns the byte offset of each line of `data`, which ends lines at LINE_END."""
    return [ByteOffset(0)] + [ByteOffset(m.end()) for m in re.finditer(LINE_END.encode(), data)]


# The code of an error, such as `E116`, as the CLI prints it and a reject header names it.
CODE = r"(?P<letter>[A-Z])(?P<number>\d{3})"
# The line and column of an error, such as `12:9`. Both count from 1.
POS = r"(?P<line>\d+):(?P<col>\d+)"


class LineCol(NamedTuple):
    """A position in a source, as fe0's `LineCol` in fe0/src/lexer.fe holds it."""

    line: int
    col: int

    @classmethod
    def matched(cls, m: re.Match[str]) -> Self:
        """Returns the position that the match `m` names. The pattern of `m` holds the groups of
        POS."""
        return cls(int(m["line"]), int(m["col"]))

    @classmethod
    def of(cls, offset: ByteOffset, source: FeSource) -> Self:
        """Returns the position of the byte offset `offset` in `source`."""
        starts = line_starts(source.encode())
        line = bisect.bisect_right(starts, offset)
        return cls(line, offset - starts[line - 1] + 1)

    def offset(self, source: FeSource) -> ByteOffset:
        """Returns the byte offset of the position in `source`, the inverse of `of`.

        Errors when the line is past the end of `source`.
        """
        starts = line_starts(source.encode())
        if self.line > len(starts):
            raise ValueError(f"line {self.line} is past the end")
        return ByteOffset(starts[self.line - 1] + self.col - 1)

    def __str__(self) -> str:
        """Returns the position as POS spells it, such as `12:9`."""
        return f"{self.line}:{self.col}"


# The letters of the phases, from phase 1 on.
PHASE_LETTERS: str = fe_string(FE0 / "src/diag.fe", "PHASE_LETTERS")


class DiagCode(NamedTuple):
    """The kind of an error of Fe0, apart from where it points."""

    # The phase letter, such as "E" in E116.
    letter: PhaseLetter
    # The number within the phase, such as 116 in E116.
    number: int

    @classmethod
    def matched(cls, m: re.Match[str]) -> Self:
        """Returns the code that the match `m` names. The pattern of `m` holds the groups of
        CODE."""
        return cls(PhaseLetter(m["letter"]), int(m["number"]))

    @classmethod
    def of_value(cls, value: int) -> Self:
        """Returns the code that `DiagCode.value()` in fe0/src/diag.fe gives as `value`, such as
        C034 for 6034. Errors with ValueError when `value` names no phase."""
        phase = value // 1000
        if not 1 <= phase <= len(PHASE_LETTERS):
            raise ValueError(f"the error code {value} names no phase")
        return cls(PhaseLetter(PHASE_LETTERS[phase - 1]), value % 1000)

    @property
    def is_syntax(self) -> bool:
        """True if Fe0's lexer or parser gives the error. False for an error of a later phase,
        which comes from a program that Fe0 parsed."""
        return self.letter in (PhaseLetter("L"), PhaseLetter("P"))

    def value(self) -> int:
        """Returns the value of the code, the inverse of `of_value`."""
        return (PHASE_LETTERS.index(self.letter) + 1) * 1000 + self.number

    def __str__(self) -> str:
        """Returns the code as CODE spells it, such as `E116`."""
        return f"{self.letter}{self.number:03}"


@dataclass(frozen=True)
class Diag:
    """An error of Fe0, as `Diag` in fe0/src/diag.fe holds it."""

    code: DiagCode
    # Where the error points.
    offset: ByteOffset

    @classmethod
    def matched(cls, m: re.Match[str], source: FeSource) -> Self:
        """Returns the error that the match `m` names in `source`. The pattern of `m` holds the
        groups of CODE and POS.

        Errors as `LineCol.offset` does.
        """
        return cls(DiagCode.matched(m), LineCol.matched(m).offset(source))

    def rejected(self) -> FeExpr:
        """Returns the Fe expression of the `difftest::CompileError` that holds the error."""
        return FeExpr(f"difftest::CompileError {{ code: {self.code.value()}, offset: {self.offset} }}")

    def describe(self, source: FeSource) -> str:
        """Returns the code, line and column of the error in `source`, such as `E116 12:9`."""
        return f"{self.code} {LineCol.of(self.offset, source)}"


def check_diag() -> None:
    r"""Checks DiagCode and Diag against the example of fe0/src/diag.fe, the decoding of a
    CompileError, and one source with `\r`."""
    e116 = DiagCode(PhaseLetter("E"), 116)
    assert str(e116) == "E116" and not e116.is_syntax
    assert DiagCode(PhaseLetter("P"), 1).is_syntax
    assert DiagCode.of_value(6034) == DiagCode(PhaseLetter("C"), 34)
    assert DiagCode.of_value(e116.value()) == e116
    at9 = Diag(e116, ByteOffset(9))
    rejected = next(d for d in ErrorDecl.all() if d.name == "CompileError")
    revert = rejected.selector + abi_encode(["uint256", "uint256"], [e116.value(), 9])
    match Failure.decode(revert):
        case CompileError() as r:
            assert r.diag == at9
        case other:
            raise AssertionError(f"{revert.hex()} decodes as {other}")
    source = FeSource("a\r\nx\ryz")
    assert LineCol(3, 2).offset(source) == 6 and LineCol.of(ByteOffset(6), source) == LineCol(3, 2)
    assert Diag(e116, ByteOffset(6)).describe(source) == "E116 3:2"
