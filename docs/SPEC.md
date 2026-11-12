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
- **[✓]** — confirmed by a probe. The probes are in `spike-*/`, and the ADRs in `docs/adr/`
  summarise what they found. The programs in `corpus/` and `corpus/reject/` are probes too (§8).

Reference toolchain: Fe 26.6.0 ([ADR 0015](adr/0015-move-to-26-6-0.md)). `tools/spikes.sh`
reruns the probes on it.

---

## 1. Lexical structure

Source text is UTF-8. Only ASCII may appear outside comments and string literals.

| Token | Definition | Notes |
|---|---|---|
| Whitespace | `[ \t]+` | Ignored |
| Newline | `(\n \| \r\n \| \r)+` | Significant: it can end a statement (§3.4) |
| Line comment | `//` up to the end of the line | Ignored, unless it starts with `///` |
| Doc comment | `///` up to the end of the line | Allowed only in some places (below) |
| Identifier | `[a-zA-Z_][a-zA-Z0-9_]*`, excluding keywords, type names and a lone `_` | |
| Decimal integer | `[0-9]+(_[0-9]+)*` | The value must fit in 256 bits |
| Hex integer | `0[xX][0-9a-fA-F]+` | No `_` separators. Must fit in 256 bits |
| String | `"` … `"` with escapes `\" \\ \n \r \t` | Only allowed as the message of `assert!`, and at most 31 bytes after decoding. Fe accepts longer messages **[✓]**; Fe0 v1 restricts them so `Error(string)` stays one data word |
| Punctuation | `( ) { } [ ] : , -> # .` | `;` is not a token: Fe 26.6.0 rejects it after a statement, even at the end of a line **[✓]**. `::` appears only in `Address::zero()`, as two `:` with no space between them. Fe reads `::` as one token and rejects `: :` **[✓]** |
| Operators | `+ - * / % ~ ! ^ & \| && \|\| < > = == !=` | |
| Compound operators | `<= >= << >> += -= *= /= %= &= \|= ^= <<= >>=` | In Fe these are joined from adjacent tokens by the parser. Fe0 requires the characters to be adjacent, with no space inside, and rejects spaced forms. Fe 26.6.0 rejects `x + = 1` too **[✓]** |

- **No block comments.** Fe's compiler lexer has none, even though the tree-sitter grammar does.
- **Doc comments.** A comment that starts with `///`, including `////`, is a doc comment. It may
  come only before an item, a contract field, `init`, `recv`, an arm, a variant or a field of a
  variant. Only newlines and other comments may come between it and what it documents. A doc
  comment may also stand at the end of the line where a contract field, `init`, `recv`, an arm,
  a variant or a variant's field ends. It then documents the next of these. It may not stand at
  the end of the line where an item ends, because only a newline or a plain comment may follow
  an item on its line (§3.1). It may also end the line of the `{` that opens a `msg`, a
  contract, a `recv` block or a variant's fields. A variant's doc comment may come before or
  after its selector, but not on the selector's line. A doc comment must come before what it
  documents, so one right before `}` or at the end of the file is a syntax error. Fe allows doc
  comments in the same places:
  - Fe accepts each of these places **[✓]**. The program `corpus/doc_comments.fe` has one of
    each.
  - Fe rejects a doc comment in a block (`1-0001`) **[✓]**. The probe is
    `corpus/reject/doc_in_block.fe`.
  - Fe rejects a doc comment before `}` (`1-0001`) **[✓]**. The probe is
    `corpus/reject/doc_documents_nothing.fe`.
  - Fe rejects a doc comment on a selector's line (`1-0001`) **[✓]**. The probe is
    `corpus/reject/doc_after_selector.fe`.
  - Fe rejects a doc comment at the end of an item's line (`1-0001`) **[V]**.
  - Fe also rejects a doc comment among binds, among parameters or `uses` entries, anywhere
    else inside `( )`, and at the end of the file **[V]**.
  - `//!` is an ordinary comment in both **[V]**.
- **Binary (`0b`) and octal (`0o`) literals** are left out of Fe0. They are valid Fe, so they
  could be added later.

**Reserved words.** These are every keyword of Fe's lexer, so Fe0 rejects any of them as an
identifier (`tools/spikes.sh` checks this list against Fe's source):

```
as true false break uses continue contract msg fn mod const static_assert if else
match for in loop where while pub return yield self Self struct enum trait impl type let var
mut ref own use extern unsafe ingot super
```

`init`, `recv`, `assert` and `with` are contextual words in Fe, not keywords. Fe0 **also
rejects them as identifiers**, which keeps the parser simple and is allowed by the subset rule.

**Type names.** `u` or `i` followed by digits, `usize`, `isize`, `bool`, `String` and
`Address` are type names, not identifiers. Fe0 rejects them wherever a name appears.

Fe's rule is narrower than Fe0's. Its primitive types are `u8`, `u16`, `u32`, `u64`, `u128`
and `u256`, the `i` types of the same widths, `usize`, `isize`, `bool` and `String`. Fe
rejects a local, parameter, function or constant named after one of them, with `8-0030` at
each use **[✓]**. A `let`, a `var` and a bind all count as locals. Fe accepts these names for
fields. It also accepts them for msgs, variants and contracts, except `bool` and `u256`
**[✓]**. Fe accepts `Address` as the name of a parameter, function or constant **[✓]**.
Widths that Fe lacks, such as `u7` and `u24`, are plain names in Fe **[✓]**. Fe0 keeps one
rule for every name, which the subset rule allows.

## 2. Types

| Type | Values | Operations |
|---|---|---|
| `u256` | 0 … 2²⁵⁶−1 | All arithmetic, bitwise and comparison operators (§4) |
| `bool` | `true`, `false` | `! && \|\| == !=` |
| `Address` | 160-bit account address | `== !=` only. `ctx.caller()` and `Address::zero()` make one (§6). Other values come from parameters, storage and return values |

- There are no other types: no signed integers or other widths, no tuples, arrays, structs,
  enums or references.
- Integer literals have type `u256`, but only where their context makes them one. Fe has no
  default integer type. It rejects a literal whose type nothing fixes, with `8-0031` **[✓]**.
- Fe0 gives `T005` for an integer whose type nothing fixes. Such an integer is built only from
  literals, operators, if-expressions and blocks. Fe0 rejects it as an expression statement
  and as the value of a `let` or `var` without a type. It also rejects a comparison of two
  such integers, in constants too. So `var i: u256 = 0` needs its type, and `1 == 1` is an
  error, as is `const B: bool = 1 == 1`.
- Fe also infers the type of `let x = 1` from later uses of `x`. Fe0 does not.
- Every expression has exactly one type, and there are no implicit conversions.

## 3. Syntax

### 3.1 Grammar

The grammar is EBNF. `{ x }` means zero or more, `[ x ]` means optional. Terminals are quoted.
`NL` is a newline token.
- The grammar leaves out doc comments (§1). It also leaves out the optional newlines inside
  `msg`, `contract` and `recv` bodies. A newline that is required, such as the one after a
  selector, is shown as `NL`.
- Fe rejects two items on one line (`1-0001`) **[✓]**. The probe is
  `corpus/reject/items_one_line.fe`. Fe accepts contract members and arms on one line **[V]**.
- Fe rejects a selector with its variant on the same line (`1-0001`) **[✓]**. The probe is
  `corpus/reject/selector_same_line.fe`.

```ebnf
program     = { NL } { item TERM { NL } } ;      (* one item per line *)
item        = [ "pub" ] ( const | function | msg | contract ) ;

const       = "const" IDENT ":" type "=" expr ;
function    = "fn" IDENT "(" [ params ] ")" [ "->" type ] block ;
params      = param { "," param } [ "," ] ;
param       = [ "_" ] IDENT ":" type ;            (* "_ x" means a positional argument, §5.4 *)

msg         = "msg" IDENT "{" [ variants ] "}" ;
variants    = variant { "," variant } [ "," ] ;
variant     = selector NL IDENT [ "{" [ fields ] "}" ] [ "->" type ] ;
selector    = "#" "[" "selector" "=" INT "]" ;
fields      = field { "," field } [ "," ] ;
field       = IDENT ":" type ;

contract    = "contract" IDENT [ effects ] "{" { cfield } [ init ] { recv } "}" ;
effects     = "uses" "(" [ effect { "," effect } [ "," ] ] ")" ;
effect      = IDENT ":" "Ctx" ;                   (* §6, "The caller" *)
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
TERM        = NL | (* before "}" or at end of input *) ;   (* see §3.4 *)

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
            | assert | caller | zero ;
if          = "if" expr block [ "else" ( if | block ) ] ;
assert      = "assert" "!" "(" expr [ "," STRING ] ")" ;
caller      = IDENT "." "caller" "(" ")" ;
zero        = "Address" "::" "zero" "(" ")" ;

CMPOP       = "==" | "!=" | "<" | ">" | "<=" | ">=" ;
AUGOP       = "+=" | "-=" | "*=" | "/=" | "%=" | "&=" | "|=" | "^=" | "<<=" | ">>=" ;
```

An expression right before the `}` of its block is the block's tail expression, not a statement.

### 3.2 Precedence

Precedence matches Fe's binding powers (`crates/tree-sitter-fe/grammar.js`). From loosest to
tightest:

`||` < `&&` < comparisons < `|` < `^` < `&` < `<<` `>>` < `+` `-` < `*` `/` `%` < unary < call

- All binary operators associate to the left.
- Comparisons do not chain: `a < b < c` is rejected. Fe rejects it too **[✓]**, with `8-0016`,
  because `bool` has no `Ord`.
- **Generic arguments.** After a name, Fe reads `<` as the start of generic arguments when
  a comma-separated list of arguments follows and `>` closes it. So it reads `x < y >> z` as
  `x<y>` followed by `> z`, and rejects it with `2-0011` **[✓]**. An argument may be a name,
  including a type name, a literal (an integer, `true` or `false`), a call, or a group in
  `( )`, `[ ]` or `{ }`. A `>>` or `>>=` closes the list as `>` does **[✓]**. Any other
  operator in an argument ends the list, so `x < y + 1 >> z` and `(x) < y >> z` are
  comparisons **[✓]**. A name right after the closing `>` also makes Fe read comparisons, so
  it accepts `g(x < y, z > x)` **[✓]**.
  When a `<` after a name may start generic arguments, Fe0 rejects it with `P011`. Fe0's rule
  is wider than Fe's. It ignores what follows the `>`, so it rejects `g(x < y, z > x)`. It also
  takes `>=` as a closer. Fe does not close the list with `>=`, so it accepts
  `g(x < y, z >= x)` **[✓]**.
- Assignment is a statement in Fe0, not an expression.

### 3.3 Left out of Fe0 (all valid Fe)

- `**`, unary `-` and `+`, `as` casts, ranges, `for` and `match`;
- method calls other than `ctx.caller()`, path calls other than `Address::zero()`, field
  access, generics and traits;
- `struct`, `enum`, `use`, `mod`, `impl`, `extern`, `unsafe`, `with` and closures;
- contract effects other than `Ctx`, `uses` on a free function, `#[payable]`, events,
  `StorageMap`, fallback arms (`_`);
- `sol("…")` selectors, which are a stretch goal
  ([ADR 0004](adr/0004-literal-selectors-first.md), `Hasher` effect).

### 3.4 Statement termination

A statement ends at a newline, right before the `}` that closes its block, as in
`{ x = 1 }`, or at the end of the file. Fe0 adopts a deliberately **strict** rule:
- A newline is ignored where the innermost open bracket is `(`. So it is ignored inside
  `( … )`, but not on the lines of a `{ … }` block inside the parentheses. A `(` inside that
  block makes newlines ignored again, until its `)`.
- Inside `( … )`, a line may end only with `(`, `,` or a binary operator, or before `)`.
  Anywhere else, the line break is an error (`L009`). Fe reads some of those line breaks
  differently, so Fe0 rejects them all **[✓]**.
- Anywhere else, a newline ends the statement if the tokens so far form a complete statement.
  Otherwise the program is a syntax error.
- A statement must end before the next one starts, so `while c { } x = 1` on one line is
  rejected.
- The `{` that opens a block must be on the same line as the header or condition before it.
  This holds for a function, `init`, arm, `recv`, `msg` and `contract` header, and for the
  condition of an `if` or `while`. `else` must be on the same line as the `}` before it.
- A line that starts with `{` may not follow a statement that ends with a name. Fe can read
  the two as a record literal of that name. So `let a: u256 = x` followed by `{ a }` is
  rejected with `8-0006` **[✓]**. Fe0 rejects it with `P012`. Fe0's rule is wider than Fe's.
  Fe accepts `1 + x` at the end of the line, and Fe0 rejects it. Both accept `(x)` and
  `x + 1` there.

So an expression may span lines only where the innermost open bracket is `(`, and only after
`(`, `,` or a binary operator, or before `)`. Fe's rule is more permissive in some places, for
example a line inside parentheses may start with `||`, so this is a valid subset.

Probed **[✓]**:
- Fe accepts a parenthesised expression spread over several lines.
- Fe also reads `let x = a` followed by `(a)` on the next line as two statements, not as the
  call `a(a)`, just as Fe0 does.
- Fe reads a newline inside a `{ … }` block in parentheses as Fe0 does. The probe
  `corpus/reject/newline_block_in_parens_call.fe` puts `g` and `(1)` on two lines of such a
  block. Fe accepts it and reads them as the two statements `g` and `(1)`, not as the call
  `g(1)`. The probe `corpus/reject/newline_block_in_parens_return.fe` puts `return` and `5`
  on two lines of such a block. Fe rejects it with `8-0013`. Fe0 rejects both probes, because
  `g` is not a value and that `return` has no value.
- Fe accepts the `{` of an `if` or `while` on the next line.
- Inside parentheses, Fe rejects a line that starts with `-` or `*`, a line break before or
  after the `:` of a call label, after `!` or `~`, and between a function's name and the `(`
  of its call. In an `if` condition, Fe ends the condition at a line break before `<`. The
  probes are `corpus/reject/line_break_*.fe`. Fe0 rejects them all with `L009`.
- `tools/newline_check.py` compares how Fe and Fe0 split programs into statements, with Fe's
  own parser. It checks the corpus, the reject programs that Fe0 parses, and generated
  programs, each also with random line breaks wherever the rule above allows one. On Nov 11,
  they split all 1,084 programs (60,630 blocks) the same way.

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
2. **Locals.** `let`, `var` and the binds of a `recv` arm declare locals. The name rules below
   apply to locals and to parameters.
   - `let` declares an immutable local and `var` a mutable one. Assigning to a `let` local is an
     error, as in Fe (`8-0018`) **[✓]**.
   - Shadowing with a new `let`/`var` is allowed **[✓]**.
   - A local's scope runs from after its declaration to the end of its block.
   - The name of a local or a parameter may not be the name of a contract field (`N005`). A
     contract field is a storage field or a `Ctx` effect. So a name never silently stops
     referring to the field. Fe accepts a local named like a storage field **[✓]**.
   - The name of a local or a parameter may not be the name of any item (`N018`), so a name in a
     body always means one declaration.
   - Fe's rule is narrower, and it differs by the kind of name. Fe reads a `let`, `var` or
     bind name that names a contract as a pattern, and rejects it (`8-0000`) **[✓]**. It
     reads a `let` or `var` name that names a constant as a pattern too, and rejects it as
     refutable (`8-0101`) **[✓]**. It reads a bind `a: n` for a constant `n` as a pattern
     too, and rejects it as refutable (`8-0153`) **[✓]**. Fe 26.5.1 accepted that bind. It ran
     the arm for any value of the field, and `n` in the body was still the constant **[✓]**.
     Fe accepts a parameter named like any item, and a local named like a function or a msg
     **[✓]**.
   - The name of a local or a parameter may not start with an uppercase letter (`N017`).
   - Fe's rule is narrower. Fe reads an uppercase local or bind that names a type or a variant
     in scope, such as `let Some` or `x: Option`, as a pattern, and rejects it **[✓]**. Fe
     accepts any other uppercase local, such as `let Foo` **[✓]**, and every uppercase
     parameter **[✓]**. Fe0 rejects them all, so that one rule covers locals and parameters alike.
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
5. **Free functions are pure.** They have no `uses` clause, so they cannot touch storage or
   read the caller (§6).
6. **Return paths.** A function with `-> T` must produce a `T` on every path, either through its
   final expression or through `return`. Otherwise it is an error (`8-0000`, type mismatch)
   **[✓]**.
7. **A tail after a diverging statement.** A block with a final expression has that
   expression's type, even when `return`, `break` or `continue` comes before it and the
   expression is never reached. A block without a final expression has unit type. When one
   of its statements diverges, the block diverges too, and then it fits any type.
   - Fe rejects `return 1` followed by `true` in a function `-> u256` (`8-0000`) **[✓]**. The
     probe is `corpus/reject/never_tail_return.fe`.
   - Fe rejects `break` followed by `5` in a loop body (`8-0031`) **[✓]**. The probe is
     `corpus/reject/never_tail_break.fe`.
   - Fe accepts `return 1` followed by `2` in a function `-> u256`, and so does Fe0 **[V]**.

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
- The `mut` fields fill storage in declaration order, from slot 0, **non-`mut` fields not
  counted** **[✓]**. Fe 26.6.0 packs them as Solidity does (#1826):
  - a `u256` takes 32 bytes, an `Address` 20 and a `bool` 1;
  - a field goes in the bytes of the current slot that follow the previous field, counted from
    the low end, when it fits there. Otherwise it starts the next slot;
  - so a `u256` always has a slot to itself, and the field after it starts a new one.
- With fields `mut a: Address, b: u256, mut c: bool, mut d: Address`, `a` is in the low 20
  bytes of slot 0, `c` in byte 20 of slot 0, and `d` in slot 1, since 21 + 20 bytes do not fit
  in 32.
- `bool` is stored as 0 or 1 **[✓]**.
- `Address` is stored with the high bits of its 20 bytes zero **[✓]**: the address `0xcc`
  alone in a slot is stored as the word `0xcc`.
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

**The caller** ([ADR 0017](adr/0017-caller.md)). A contract may declare `Ctx` effects, as in
`contract Owned uses (ctx: Ctx) {`. `init` and arms grant a `Ctx` effect in their `uses` as they
grant a storage field.
- `ctx.caller()` is the address that called the contract. In `init`, it is the address that
  deploys the contract. A body that reads it must list `ctx` in its `uses`, as for a storage
  field (`E116`). Fe rejects such a body too, because `ctx` is an undefined name there
  (`8-0012`) **[✓]**.
- `Address::zero()` is the address 0. It needs no effect, so a free function may use it. It is
  not a constant expression (`C001`). Fe rejects it in a constant too, because `zero` is not a
  `const fn` (`3-0024`) **[✓]**.
- A `Ctx` effect is not a value. A name that refers to one is an error (`N003`), except before
  `.caller()`. Assigning to one is an error (`N014`), even when `uses` names it `mut`. Fe
  rejects both **[✓]**.
- A `Ctx` effect takes no storage. The storage fields' slots are the same as without it.
- A storage field may not take the name of a `Ctx` effect (`N001`). Neither may a local, a
  parameter or a bind (§5.2). Fe rejects such a storage field, bind or parameter **[✓]**. It
  accepts such a local **[✓]**.
- Fe0 rejects a `Ctx` effect written `mut Ctx` (`P002`) and the same `Ctx` effect declared
  twice (`N001`). Fe accepts both **[✓]**. Other methods of `Ctx`, such as `ctx.origin()`, are
  left out of Fe0 (§3.3). So is `uses` on a free function (§5.5).

**Messages and dispatch.**
- A `recv M` block must have exactly one arm per variant of `M` **[✓]** (the "missing variants"
  error).
- Arm bindings name the variant's fields: `Set { a: x }` binds field `a` to the local `x`, and
  `Set { a }` binds it to the local `a`.
- An arm's return type must match its variant's.
- A selector must fit in 32 bits (`9-0001`) **[✓]**. Selectors must be unique within a msg
  (`9-0004`) **[✓]** and across all msgs the contract receives (`8-0047`) **[✓]**.
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
- A program must declare a contract. Fe accepts a module without one, so this rule is Fe0's
  own.

## 7. Diagnostics

- Fe0 stops at the first error. Warnings (unused `uses` entries) do not stop it.
- It reports `line:col`, a stable error code (`L` lexical, `P` parse, `N` name, `T` type, `E`
  effect, `C` const-eval, `G` generation) and a one-line message.
- Error codes are part of the test suite. Matching Fe's message wording is not a goal.

## 8. Conformance testing

The subset rule is tested two ways.

- **Accepted programs.** A differential test compiles one source with Fe and with Fe0, the
  latter running on the EVM, and deploys both builds with the same constructor arguments and
  value. Either both deployments create a contract or neither does. Then both contracts get
  the same calls, and each call must give the same success flag and the same return or
  revert data, byte for byte. Storage effects show through the later calls that read them.
- **Rejected programs.** Fe0 must give the expected error code at the expected position, and
  Fe must reject the program too, unless the rule is one that Fe0 adds on top of Fe (such as
  §5.2's ban on locals named like fields). Then Fe must accept it.

The aim is a test of one of these kinds for every rule above that has a [✓] mark. The tests are
in `corpus/`, `corpus/reject/` and `fe0/src/codegen_tests.fe`, and DESIGN.md §10 describes how
the harness runs them.

## 9. Open questions

Answered by the probes in `spike-conform/` (Oct 28): shifts by 256 or more, left-to-right
evaluation order, `uses` duplicates and unused entries, and extra calldata bytes. Also answered
(Oct 28): `init` with missing or malformed arguments, and `Address` storage alignment.

The newline rule of §3.4 was answered on Nov 11, by `tools/newline_check.py`. It found that Fe
reads some line breaks inside parentheses differently, and Fe0's rule became narrower. No
question is open.
