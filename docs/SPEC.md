# Fe0 language specification (draft 0)

Fe0 is a small subset of [Fe](https://github.com/argotorg/fe) for writing EVM contracts. The
Fe0 compiler is written in Fe.

**The subset rule.** Every program Fe0 accepts must also be accepted by the official compiler,
and must behave the same way: the same storage effects, return data and revert data for every
call. Fe0 may reject programs that Fe accepts, never the other way round. Where this document
and the official compiler disagree, the compiler wins and the document is fixed.

Marks used below:
- **[V]** — behaviour not yet confirmed against the official compiler. Each one becomes a
  differential test before it is relied on.
- **[✓]** — confirmed by a probe. The probes are in `spike-*/`; the ADRs in `docs/adr/`
  summarise what they found.

Reference toolchain: Fe 26.5.1. Probes ran on master `d217a51bf`.

---

## 1. Lexical structure

Source text is UTF-8. Only ASCII may appear outside comments and string literals.

| Token | Definition | Notes |
|---|---|---|
| Whitespace | `[ \t]+` | Ignored |
| Newline | `(\n \| \r\n \| \r)+` | Significant: it can end a statement (§3.4) |
| Line comment | `//` up to the end of the line | `///` doc comments are lexed the same way and ignored |
| Identifier | `[a-zA-Z_][a-zA-Z0-9_]*`, excluding keywords and a lone `_` | |
| Decimal integer | `[0-9]+(_[0-9]+)*` | The value must fit in 256 bits |
| Hex integer | `0[xX][0-9a-fA-F]+` | No `_` separators. Must fit in 256 bits |
| String | `"` … `"` with escapes `\" \\ \n \r \t` | Only allowed as the message of `assert!`, and at most 31 bytes after decoding. Fe accepts longer messages **[✓]**; Fe0 v1 restricts them so `Error(string)` stays one data word |
| Punctuation | `( ) { } [ ] : , -> # . ;` | |
| Operators | `+ - * / % ~ ! ^ & \| && \|\| < > = == !=` | |
| Compound operators | `<= >= << >> += -= *= /= %= &= \|= ^= <<= >>=` | In Fe these are joined from adjacent tokens by the parser. Fe0 requires the characters to be adjacent, with no space inside, and rejects spaced forms. That is safe under the subset rule |

- **No block comments.** Fe's compiler lexer has none, even though the tree-sitter grammar does.
- **Binary (`0b`) and octal (`0o`) literals** are left out of Fe0. They are valid Fe, so they
  could be added later.

**Reserved words.** These are every keyword of Fe's lexer, so Fe0 rejects any of them as an
identifier: `as true false break uses continue contract msg fn mod const static_assert if else
match for in where while pub return yield self Self struct enum trait impl type let var mut ref
own use extern unsafe ingot super`.

`init`, `recv`, `assert` and `with` are contextual words in Fe, not keywords. Fe0 **also
rejects them as identifiers**, which keeps the parser simple and is allowed by the subset rule.

## 2. Types

| Type | Values | Operations |
|---|---|---|
| `u256` | 0 … 2²⁵⁶−1 | All arithmetic, bitwise and comparison operators (§4) |
| `bool` | `true`, `false` | `! && \|\| == !=` |
| `Address` | 160-bit account address | `== !=` only. Fe0 has no way to construct one; values only come from parameters, storage and return values |

- There are no other types: no signed integers or other widths, no tuples, arrays, structs,
  enums or references.
- Integer literals have type `u256`.
- Every expression has exactly one type, and there are no implicit conversions.

## 3. Syntax

### 3.1 Grammar

The grammar is EBNF. `{ x }` means zero or more, `[ x ]` means optional. Terminals are quoted.
`NL` is a newline token.

```ebnf
program     = { NL } { item { NL } } ;
item        = [ "pub" ] ( const | function | msg | contract ) ;

const       = "const" IDENT ":" type "=" expr TERM ;
function    = "fn" IDENT "(" [ params ] ")" [ "->" type ] block ;
params      = param { "," param } [ "," ] ;
param       = [ "_" ] IDENT ":" type ;            (* "_ x" means a positional argument, §5.4 *)

msg         = "msg" IDENT "{" [ variants ] "}" ;
variants    = variant { "," variant } [ "," ] ;
variant     = selector IDENT [ "{" [ fields ] "}" ] [ "->" type ] ;
selector    = "#" "[" "selector" "=" INT "]" ;
fields      = field { "," field } [ "," ] ;
field       = IDENT ":" type ;

contract    = "contract" IDENT "{" { cfield } [ init ] { recv } "}" ;
cfield      = "mut" IDENT ":" type [ "," ] ;         (* v1: mut only, see §6 *)
init        = "init" "(" [ params ] ")" [ uses ] block ;
recv        = "recv" IDENT "{" { arm } "}" ;
arm         = IDENT "{" [ binds ] "}" [ "->" type ] [ uses ] block ;
binds       = bind { "," bind } [ "," ] ;
bind        = IDENT [ ":" IDENT ] ;
uses        = "uses" "(" [ use { "," use } [ "," ] ] ")" ;
use         = [ "mut" ] IDENT ;

type        = "u256" | "bool" | "Address" ;

block       = "{" { NL } { stmt { NL } } [ expr { NL } ] "}" ;
stmt        = ( "let" | "var" ) IDENT [ ":" type ] "=" expr TERM
            | "while" expr block TERM
            | "return" [ expr ] TERM
            | "break" TERM | "continue" TERM
            | place "=" expr TERM
            | place AUGOP expr TERM
            | expr TERM ;
place       = IDENT ;
TERM        = ";" | NL | (* before "}" or at end of input *) ;   (* see §3.4 *)

expr        = or ;
or          = and { "||" and } ;
and         = cmp { "&&" cmp } ;
cmp         = bitor [ CMPOP bitor ] ;             (* comparisons don't chain *)
bitor       = bitxor { "|" bitxor } ;
bitxor      = bitand { "^" bitand } ;
bitand      = shift { "&" shift } ;
shift       = add { ( "<<" | ">>" ) add } ;
add         = mul { ( "+" | "-" ) mul } ;
mul         = unary { ( "*" | "/" | "%" ) unary } ;
unary       = ( "!" | "~" ) unary | primary ;
args        = arg { "," arg } [ "," ] ;
arg         = [ IDENT ":" ] expr ;
primary     = INT | "true" | "false" | IDENT "(" [ args ] ")" | IDENT | "(" expr ")" | block | if
            | assert ;
if          = "if" expr block [ "else" ( if | block ) ] ;
assert      = "assert" "!" "(" expr [ "," STRING ] ")" ;

CMPOP       = "==" | "!=" | "<" | ">" | "<=" | ">=" ;
AUGOP       = "+=" | "-=" | "*=" | "/=" | "%=" | "&=" | "|=" | "^=" | "<<=" | ">>=" ;
```

An expression right before `}` with no `;` is the block's tail expression, not a statement.

### 3.2 Precedence

Precedence matches Fe's binding powers (`crates/tree-sitter-fe/grammar.js`). From loosest to
tightest:

`||` < `&&` < comparisons < `|` < `^` < `&` < `<<` `>>` < `+` `-` < `*` `/` `%` < unary < call

- All binary operators associate to the left.
- Comparisons do not chain: `a < b < c` is rejected. Fe rejects it too **[✓]**, with `8-0016`,
  because `bool` has no `Ord`.
- Assignment is a statement in Fe0, not an expression.

### 3.3 Left out of Fe0 (all valid Fe)

- `**`, unary `-` and `+`, `as` casts, ranges, `for` and `match`;
- method calls and field access, generics and traits;
- `struct`, `enum`, `use`, `mod`, `impl`, `extern`, `unsafe`, `with` and closures;
- contract-level `uses`, `#[payable]`, events, `StorageMap`, fallback arms (`_`);
- `sol("…")` selectors, which are a stretch goal
  ([ADR 0004](adr/0004-literal-selectors-first.md), `Hasher` effect).

### 3.4 Statement termination

A statement ends at `;`, at a newline, right before the `}` that closes its block, as in
`{ x = 1 }`, or at the end of the file. Fe0 adopts a deliberately **strict** rule:
- Inside `( … )`, newlines are ignored.
- Anywhere else, a newline ends the statement if the tokens so far form a complete statement.
  Otherwise the program is a syntax error.
- A statement must end before the next one starts, so `while c { } x = 1` on one line is
  rejected.
- The `{` that opens a block must be on the same line as the header or condition before it.
  This holds for a function, `init`, arm, `recv`, `msg` and `contract` header, and for the
  condition of an `if` or `while`. `else` must be on the same line as the `}` before it.

So an expression may span lines only inside parentheses. Fe's automatic semicolon rule is more
permissive, for example a line may start with `||`, so this is a valid subset.

Probed **[✓]**:
- Fe accepts a parenthesised expression spread over several lines.
- Fe also reads `let x = a` followed by `(a)` on the next line as two statements, not as the
  call `a(a)`, just as Fe0 does.
- Fe accepts the `{` of an `if` or `while` on the next line.

Still **[V]**: a systematic check that Fe reads every Fe0-accepted line break the same way.
This becomes a parser differential test over the corpus.

## 4. Expression semantics

**Evaluation order.**
- Operands and call arguments are evaluated left to right, each exactly once **[✓]**. With
  `z = 0`, both `1 / z + (z - 1)` and `pair(1 / z, z - 1)` revert with `Panic(0x12)` (the left
  operand), not `0x11`.
- `&&` and `||` short-circuit.

**Arithmetic on `u256`** is checked. Probed failure behaviour:

| Operation | On failure |
|---|---|
| `+` overflow, `-` underflow, `*` overflow | Revert with `Panic(0x11)` **[✓]** |
| `/` or `%` by zero | Revert with `Panic(0x12)` **[✓]** |
| `&` `\|` `^` `~` | Never fail |
| `<<`, `>>` | Never fail. Bits shifted out are discarded (`3 << 255` = 2²⁵⁵), and a shift by 256 or more gives 0, as with the EVM's `SHL`/`SHR` **[✓]** |

- `Panic(c)` means the revert data `0x4e487b71 ‖ uint256(c)`, Solidity's encoding.
- Compound assignment `x op= e` means `x = x op e`, with the same checks. The target is always
  an identifier, so the question of evaluating it once does not arise in Fe0.

**Comparisons** are unsigned on `u256`. On `Address`, only equality is allowed.

**`if`.** `if c { a } else { b }` is an expression when both branches produce values of the same
type. Without `else`, it has unit type and may only be used as a statement.

**Blocks.**
- A block's value is its final expression, if there is one.
- A function or arm body's final expression is its return value.

**`assert!(c)`** reverts with `Panic(0x01)` when `c` is false **[✓]**.

**`assert!(c, "msg")`** reverts with `Error(string)` instead **[✓]**: `0x08c379a0` followed by the
ABI-encoded string.

## 5. Names, scopes and checking

1. **Items** (`const`, `fn`, `msg`, `contract`) form one namespace and may be declared in any
   order. Duplicates are an error.
2. **Locals.**
   - `let` declares an immutable local and `var` a mutable one. Assigning to a `let` local is an
     error, as in Fe (`8-0018`) **[✓]**.
   - Shadowing with a new `let`/`var` is allowed **[✓]**.
   - A local's scope runs from after its declaration to the end of its block.
   - A local may not take the name of a storage field. Fe accepts this **[✓]**, but Fe0 rejects
     it, so a name never silently stops referring to storage.
3. **Constants** are evaluated at compile time with the §4 semantics. Overflow is a compile-time
   error (`3-0034`), and so is division by zero (`3-0025`) **[✓]**.
   - A constant may refer only to earlier constants and literals.
   - Fe accepts forward references **[✓]**; Fe0 keeps the restriction, which is safe under the
     subset rule.
4. **Function calls.**
   - A parameter written `_ x: T` is positional: call it as `f(e)`.
   - A parameter written `x: T` is labelled: call it as `f(x: e)`, or as `f(x)` when the argument
     is the identifier `x` itself **[✓]**. Leaving out a required label is `8-0024` **[✓]**.
   - Arguments must follow the parameter order. Swapped labels are `8-0024` **[✓]**.
   - Recursion is allowed. Fe0 adds no limit beyond EVM gas and stack depth.
5. **Free functions are pure.** They have no `uses` clause and cannot touch storage.
6. **Return paths.** A function with `-> T` must produce a `T` on every path, either through its
   final expression or through `return`. Otherwise it is an error (`8-0000`, type mismatch)
   **[✓]**.

## 6. Contracts and effects

```fe
msg CounterMsg {
    #[selector = 0xd09de08a]
    Increment {},
    #[selector = 0x6d4ce63c]
    Get -> u256,
}

contract Counter {
    mut count: u256,

    init() uses (mut count) {
        count = 0
    }

    recv CounterMsg {
        Increment {} uses (mut count) {
            count += 1
        }
        Get {} -> u256 uses (count) {
            count
        }
    }
}
```

**Storage.**
- **Fe0 v1 requires every contract field to be `mut`.**
  - Fe keeps non-`mut` fields out of storage entirely **[✓]**. Their values are written into the
    deployed runtime code during `init` and read with `CODECOPY`, like Solidity immutables
    (`spike-layout/src/immut.fe`).
  - Supporting them means appending values to the runtime code at deploy time, which is a
    stretch goal.
- The *i*-th `mut` field (counting from 0, in declaration order, **non-`mut` fields not
  counted**) lives in storage slot *i*, one 32-byte slot per field with no packing **[✓]**. With
  fields `a, mut b, c, mut d`, `b` is in slot 0 and `d` in slot 1.
- `bool` is stored as 0 or 1 **[✓]**.
- `Address` is stored right-aligned with the high bits zero **[✓]**: the address `0xcc` is
  stored as the word `0xcc`.
- For when immutables are added: a field declared without `mut` is read-only after `init` **[✓]**.
  - `init` may still write it, with `uses (mut v)`.
  - An arm that declares `mut v` on it is rejected (`8-0085`).

**Effects (`uses`).** Every `init` and arm body is checked:
- Reading field `f` requires `f` or `mut f` in its `uses`. Otherwise it is an error, as in Fe
  (`8-0116`) **[✓]**.
- Assigning to `f` requires `mut f` (`8-0018`) **[✓]**.
- Listing a field the contract doesn't have is an error (`8-0051`) **[✓]**.
- An arm binding with the same name as a field in `uses` is an error. Fe reports this ("a name
  that an effect binds and that a parameter … also binds").
- Fe accepts *unused* `uses` entries **[✓]**, so Fe0 reports them only as warnings.
- Fe also accepts *duplicate* entries (`uses (v, v)`) **[✓]**; Fe0 rejects them.

This check is the point of Fe0.

**Messages and dispatch.**
- A `recv M` block must have exactly one arm per variant of `M` **[✓]** (the "missing variants"
  error).
- Arm bindings name the variant's fields: `Set { a: x }` binds field `a` to the local `x`, and
  `Set { a }` binds it to the local `a`.
- An arm's return type must match its variant's.
- Every variant's arm pattern is written with braces, `Name {}` even when it has no fields. That
  avoids an ambiguity in Fe's grammar **[✓]**.

The runtime dispatcher matches the official one (`mir/src/runtime/synthetic.rs:745`):

1. If `calldatasize < 4`, revert with empty data **[✓]**.
2. Compute `selector = calldataload(0) >> 224` and jump to the matching arm.
3. If no arm matches, revert with empty data **[✓]**.
4. Arguments are decoded as static ABI words in field order, starting at calldata offset 4.
   Probed **[✓]**:
   - **Short calldata** (fewer argument words than fields): revert with empty data.
   - **Extra bytes** after the last argument: ignored, and the call succeeds.
   - **A `bool` word other than 0 or 1:** revert with empty data.
   - **An `Address` word with any of its upper 96 bits set:** revert with empty data.
   - **A call carrying `msg.value > 0`:** revert with empty data, because arms are non-payable.
5. On success, a `u256`, `bool` or `Address` return value comes back as one ABI word **[✓]**. An
   arm without a return type returns empty data **[✓]**.

**Deployment.**
- The initcode runs `init` with its static ABI arguments, which are appended to the initcode,
  then returns the runtime code.
  - This layout is documented in the 26.5.0 changelog: `init_code_hash` hashes "the embedded
    creation code of `C` followed by its ABI-encoded constructor arguments".
  - Probed **[✓]** (`spike-conform/src/init_args.fe`): the initcode handles arguments the same
    way the dispatcher handles calldata.
    - Missing arguments, too few argument words, a `bool` word other than 0 or 1, or an
      `Address` word with upper bits set: the creation reverts, so CREATE returns address 0.
    - Extra trailing bytes are ignored.
    - Deploying with `value > 0` fails, because `init` is non-payable.
- A contract without `init` gets a no-op one.
- An ingot holds one contract.

## 7. Diagnostics

- Fe0 stops at the first error.
- It reports `line:col`, a stable error code (`L` lexical, `P` parse, `N` name, `T` type, `E`
  effect, `C` const-eval) and a one-line message.
- Error codes are part of the test suite. Matching Fe's message wording is not a goal.

## 8. Conformance testing

Every rule above that has a [V] or [✓] mark has at least one differential test: the same source
is compiled by Fe (`evm.create2<C>`) and by Fe0 (running on the EVM, then `create_raw`). Both
contracts are sent the same calls, and the test asserts identical success/revert status, return
data, revert data and storage reads. PLAN.md §5 describes the harness.

## 9. Open questions

Answered by the probes in `spike-conform/` (Oct 28): shifts by 256 or more, left-to-right
evaluation order, `uses` duplicates and unused entries, and extra calldata bytes. Still open:

1. The **newline rule** (§3.4): does Fe read every Fe0-accepted line break the same way? Plan:
   run a parser differential test over the whole corpus, including generated programs.

Also answered (Oct 28): `init` with missing or malformed arguments, and `Address` storage
alignment.
