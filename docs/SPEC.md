# Fe0 language specification (draft 0)

Fe0 is a small subset of [Fe](https://github.com/argotorg/fe) for writing EVM contracts. The
Fe0 compiler is written in Fe.

**The subset rule.** Every program Fe0 accepts must also be accepted by the official compiler,
and must behave the same way: for every deployment and call, the same success or failure, return
or revert data, logs and storage writes. Fe0 may reject programs that Fe accepts, never the
other way round. Where this document and the official compiler disagree, the compiler wins and
the document is fixed.
- The rule holds given enough gas. The two builds use different amounts of gas, so a call
  with a tight gas limit may fail under one and succeed under the other.
- The rule holds below Fe's recursion limit. Fe keeps return addresses on the EVM stack, and
  Fe0 keeps frames in memory. So a call that recurses past the stack's limit reverts under Fe
  and succeeds under Fe0 ([ADR 0021](adr/0021-frames-gas-and-depth.md) gives the depth).

Marks used below:
- **[V]** — behaviour not yet confirmed against the official compiler. Each one becomes a
  differential test before it is relied on.
- **[✓]** — confirmed by a probe. The probes are in `spike-*/`, and the ADRs in `docs/adr/`
  summarise what they found. The programs in `corpus/` and `corpus/reject/` are probes too (§8).

Reference toolchain: Fe 26.7.0 ([ADR 0022](adr/0022-move-to-26-7-0.md)). `tools/spikes.sh`
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
| Octal integer | `0[oO][0-7]+` | No `_` separators. Must fit in 256 bits |
| Binary integer | `0[bB][01]+` | No `_` separators. Must fit in 256 bits |
| String | `"` … `"` with escapes `\" \\ \n \r \t` | Only allowed as the message of `assert!` |
| Punctuation | `( ) { } [ ] : , -> # .` | `;` is not a token: Fe rejects it after a statement, even at the end of a line **[✓]**. `::` appears only in `Address::zero()` and in the `M::V` of a call (§6, "Calls"), as two `:` with no space between them. Fe reads `::` as one token and rejects `: :` **[✓]** |
| Operators | `+ - * / % ~ ! ^ & \| && \|\| < > = == !=` | |
| Compound operators | `<= >= << >> += -= *= /= %= &= \|= ^= <<= >>=` | In Fe these are joined from adjacent tokens by the parser. Fe0 requires the characters to be adjacent, with no space inside, and rejects spaced forms. Fe rejects `x + = 1` too **[✓]** |

- **A plain comment before a name.** The name of a variant or of a field may not come right
  after a plain comment line when a doc comment or an attribute comes before that line. A
  contract field counts from its `mut`. A doc comment after the plain comment line makes it
  allowed, and so does a plain comment at the end of the line before. Fe rejects the other
  cases (`1-0001`) **[✓]**:
  - after a selector, also with a doc comment in between. The probes are
    `corpus/reject/comment_after_selector.fe` and `corpus/reject/comment_after_selector_doc.fe`;
  - after `#[indexed]`, or after a doc comment before a field, also one at the end of the line
    before. The probes are the `corpus/reject/comment_before_*.fe` programs.

  Fe accepts a plain comment line in the same place before an item, `init`, `recv`, an arm, a
  selector, `#[indexed]` or an event's `struct`, and before a name with no doc comment or
  attribute ahead of it **[✓]**. Fe0 allows all of these. The probes are
  `corpus/doc_comments.fe` and, for a field with no doc comment, `corpus/amm.fe`.
- **No block comments.** Fe's compiler lexer has none, even though the tree-sitter grammar does.
- **Doc comments.** A comment that starts with `///`, including `////`, is a doc comment. It may
  come only before an item, a contract field, `init`, `recv`, an arm, a variant or a field of a
  variant or of an event. Only newlines and other comments may come between it and what it
  documents, except a plain comment line right before a name (above). A doc comment may also
  stand at the end of the line where a contract field, `init`, `recv`, an arm, a variant, a
  variant's field or an event's field ends. It then documents the next of these. It may not
  stand at the end of the line where an item ends, because only a newline or a plain comment may
  follow an item on its line (§3.1). It may also end the line of the `{` that opens a `msg`, an
  event, a contract, a `recv` block or a variant's fields. A variant's doc comment may come
  before or after its selector, but not on the selector's line. In the same way, an event's doc
  comment may come before or after its `#[event]`, and the doc comment of an event's field may
  come before or after its `#[indexed]`. A doc comment must come before what it documents, so
  one right before `}` or at the end of the file is a syntax error. Fe allows doc comments in
  the same places:
  - Fe accepts each of these places **[✓]**. The program `corpus/doc_comments.fe` has one of
    each.
  - Fe rejects a doc comment in a block (`1-0001`) **[✓]**. The probe is
    `corpus/reject/doc_in_block.fe`.
  - Fe rejects a doc comment before `}` (`1-0001`) **[✓]**. The probe is
    `corpus/reject/doc_documents_nothing.fe`.
  - Fe rejects a doc comment on a selector's line (`1-0001`) **[✓]**. The probe is
    `corpus/reject/doc_after_selector.fe`.
  - Fe rejects a doc comment at the end of an item's line (`1-0001`) **[✓]**. The probe is
    `corpus/reject/doc_item_line.fe`.
  - Fe also rejects a doc comment among binds, among parameters or `uses` entries, anywhere
    else inside `( )`, and at the end of the file (`1-0001`) **[✓]**. The probes are the other
    `corpus/reject/doc_*.fe`.
  - `//!` is an ordinary comment in both **[✓]**. The probe is `corpus/one_line.fe`.

**Reserved words.** These are every keyword of Fe's lexer, so Fe0 rejects any of them as an
identifier (`tools/spikes.sh` checks this list against Fe's source):

```
as true false break uses continue contract msg fn mod const static_assert if else
match for in loop where while pub return yield self Self struct enum trait impl type let var
mut ref own use extern unsafe ingot super
```

`init`, `recv`, `assert` and `with` are contextual words in Fe, not keywords, so they are
identifiers in Fe0 too **[✓]**. The probe is `corpus/contextual_words.fe`. The grammar of §3.1
still gives three of them a fixed meaning in places where no name can stand. In a contract body,
every field starts with `mut`, so `init` and `recv` there start an `init` and a `recv` block.
And `assert` followed by `!` starts an `assert!`.

**Type names.** Fe's primitive types are `u8`, `u16`, `u32`, `u64`, `u128` and `u256`, the
`i` types of the same widths, `usize`, `isize`, `bool` and `String`. These and `Address` are
type names, not identifiers. Fe0 rejects them wherever a name appears. Other widths, such as
`u7` and `u24`, are plain names, as in Fe **[✓]**.

Fe's rule is narrower than Fe0's. Fe rejects a local, parameter, function or constant named
after a primitive type, with `8-0030` at each use **[✓]**. A `let`, a `var` and a bind all count
as locals. Fe accepts a local that nothing uses when the local has the type it is named after,
as in `let u256: u256 = x` **[✓]**. The probe is `corpus/reject/type_name_unused_let.fe`. Fe
rejects an unused one of another type with `8-0000` **[✓]**. The probe is
`corpus/reject/type_name_unused_let_other_type.fe`. Fe accepts these names for fields. It also
accepts them for msgs, variants and contracts, except `bool` and `u256` **[✓]**. Fe accepts
`Address` as the name of a parameter, function or constant **[✓]**. Fe0 keeps one rule for every
name, which the subset rule allows.

## 2. Types

| Type | Values | Operations |
|---|---|---|
| `u256` | 0 … 2²⁵⁶−1 | All arithmetic, bitwise and comparison operators (§4) |
| `bool` | `true`, `false` | `! && \|\| == !=` |
| `Address` | 160-bit account address | `== !=`, and `a.call(…)` (§6, "Calls"). `Address::zero()` and the methods of `Ctx` that return an `Address` make one (§6, "The caller"). Other values come from parameters, storage and return values |

- `!` takes a `bool`, and `~ & | ^` take `u256`s. Fe also accepts `!` on a `u256` and
  `& | ^` on `bool`s **[✓]**, and Fe0 rejects them (`T001`). The probes are
  `corpus/reject/bang_u256.fe` and `corpus/reject/bitand_bool.fe`.
- Fe0 has no unit value. A call of a function without a return type, an `if` without `else`,
  `log.emit(…)` and a call of a variant without a return type have no value. Fe0 rejects one
  where a value is needed (`T003`), as in `let x = g()`. Fe gives them the type `()` and
  accepts `let x = g()` **[✓]**. The probe is `corpus/reject/unit_as_value.fe`.
- A contract field may also be a map, `StorageMap<K, V>` (§6, "Maps").
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
  `msg`, `contract`, `recv` and event bodies. A newline that is required, such as the one after
  a selector, is shown as `NL`.
- Fe rejects two items on one line (`1-0001`) **[✓]**. The probe is
  `corpus/reject/items_one_line.fe`. Fe accepts contract members and arms on one line **[✓]**.
  The probe is `corpus/one_line.fe`.
- Fe rejects a selector with its variant on the same line (`1-0001`) **[✓]**. The probe is
  `corpus/reject/selector_same_line.fe`. It also rejects `#[event]` with its struct on the
  same line, and `#[indexed]` with its field (`1-0001`) **[✓]**. The probes are
  `corpus/reject/event_attr_same_line.fe` and `corpus/reject/indexed_same_line.fe`.

```ebnf
program     = { NL } { item TERM { NL } } ;      (* one item per line *)
item        = [ "pub" ] ( const | function | msg | contract ) | event ;

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
effect      = IDENT ":" [ "mut" ] ( "Ctx" | "Log" | "Call" ) ;  (* §6, "The caller", "Events", "Calls" *)
cfield      = "mut" IDENT ":" ( type | map ) [ "," ] ;   (* v1: mut only, see §6 *)
event       = "#" "[" "event" "]" NL [ "pub" ] "struct" IDENT "{" [ efields ] "}" ;
efields     = efield { "," efield } [ "," ] ;
efield      = [ "#" "[" "indexed" "]" NL ] IDENT ":" type ;
map         = "StorageMap" "<" type "," type ">" ;  (* §6, "Maps" *)
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
place       = IDENT | index | "(" place ")" ;
TERM        = NL | (* before "}" or at end of input *) ;   (* see §3.4 *)

expr        = or ;
or          = and { "||" and } ;
and         = cmp { "&&" cmp } ;
cmp         = bitor { CMPOP bitor } ;
bitor       = bitxor { "|" bitxor } ;
bitxor      = bitand { "^" bitand } ;
bitand      = shift { "&" shift } ;
shift       = add { ( "<<" | ">>" ) add } ;
add         = mul { ( "+" | "-" ) mul } ;
mul         = unary { ( "*" | "/" | "%" ) unary } ;
unary       = ( "!" | "~" | "+" ) unary | primary ;
args        = arg { "," arg } [ "," ] ;
arg         = [ IDENT ":" ] expr ;
primary     = INT | "true" | "false" | IDENT "(" [ args ] ")" | IDENT | "(" expr ")" | block | if
            | assert | ctx_read | zero | index | emit | msg_call ;
if          = "if" expr block [ "else" ( if | block ) ] ;
assert      = "assert" "!" "(" expr [ "," STRING ] ")" ;
ctx_read    = IDENT "." IDENT "(" ")" ;   (* a method of Ctx other than emit and call, which have their own rules; §6, "The caller" *)
zero        = "Address" "::" "zero" "(" ")" ;
index       = IDENT "[" expr "]" ;
emit        = IDENT "." "emit" "(" IDENT "{" [ args ] "}" ")" ;   (* §6, "Events" *)
msg_call    = IDENT "." "call" "(" IDENT "::" IDENT "{" [ args ] "}" ")" ;   (* §6, "Calls" *)

CMPOP       = "==" | "!=" | "<" | ">" | "<=" | ">=" ;
AUGOP       = "+=" | "-=" | "*=" | "/=" | "%=" | "&=" | "|=" | "^=" | "<<=" | ">>=" ;
```

An expression right before the `}` of its block is the block's tail expression, not a statement.

A place may stand in parentheses, as in `(m[k]) = 1`. Fe accepts that too **[✓]**. The probe
is the arm `Order` of `corpus/maps.fe`. Fe also accepts `(m)[k] = 1`, and Fe0 rejects it
**[✓]**. The probe is `corpus/reject/map_paren_map.fe`.

### 3.2 Precedence

Precedence matches Fe's binding powers (`crates/tree-sitter-fe/grammar.js`). From loosest to
tightest:

`||` < `&&` < comparisons < `|` < `^` < `&` < `<<` `>>` < `+` `-` < `*` `/` `%` < unary < call
and index

- All binary operators associate to the left, comparisons included, as in Fe. So `a < b == true`
  is `(a < b) == true`. The types must fit at each step: `a < b < c` compares the `bool` `a < b`
  with `c`. Fe rejects that with `8-0016`, because `bool` has no `Ord` **[✓]**, and Fe0 rejects
  it with `T001`. Both accept `a < b == true` and `a == b == true` **[✓]**. The probes are
  `corpus/reject/chained_comparison.fe` and `corpus/chained_comparisons.fe`.
- Unary `+` takes a `u256` and gives it back unchanged. Fe rejects it on `bool` and `Address`
  with `8-0052` **[✓]**. The probes are `corpus/unary_plus.fe`, `corpus/reject/plus_bool.fe`
  and `corpus/reject/plus_address.fe`. Fe has no unary `-` on `u256`: it rejects `-x` with
  `8-0016`, because `u256` has no `Neg` **[✓]**. The probe is `corpus/reject/minus_u256.fe`.
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
  `g(x < y, z >= x)` **[✓]**. Fe0 also reads a name followed by `[ ]` as an argument, as it
  reads a call. Fe does not, so it accepts `k < m[k] >> 1` **[✓]**. The probe is
  `corpus/reject/generics_index.fe`.
- Assignment is a statement in Fe0, not an expression.

### 3.3 Left out of Fe0 (all valid Fe)

- `**`, `as` casts, ranges, `for` and `match`;
- method calls other than the methods of `Ctx` in §6, `log.emit(…)` and `a.call(…)`, path
  calls other than `Address::zero()`, field access, generics and traits;
- the other ways to call a contract: `try_call`, `static`, `call_with_default`, a call with a
  set gas or value, a call on an address that is not a name, such as `ctx.caller().call(…)`,
  and a msg value that is not written in the call, such as `let m = M::V { … }`;
- structs other than events, struct values, `enum`, `use`, `mod`, `impl`, `extern`, `unsafe`,
  `with` blocks and closures;
- contract effects other than `Ctx`, `Log` and `Call`, `uses` on a free function, `#[payable]`,
  fallback arms (`_`);
- events with fields of other types, such as arrays and strings;
- maps anywhere but as a contract field's type, maps of maps, tuple keys, key and value types
  other than `u256`, `bool` and `Address`, and the methods of `StorageMap` (`get`, `set`,
  `remove`);
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
- Where a newline can end a statement, a line may not start with `+`. Fe joins such a line
  onto the one before, so it reads `let b = a` followed by `+b` as `let b = a + b` **[✓]**.
  The probe is `corpus/reject/plus_line_start.fe`. Fe accepts `+` at the start of the first
  line of a block, where there is no line before to join **[✓]**. Fe0 rejects it there as
  well (`corpus/reject/plus_block_start.fe`). Inside parentheses, `g(x,` followed by `+x)` is
  a unary plus in both **[✓]**. The probe is the arm `Plus` of `corpus/unary_plus.fe`.
- A statement must end before the next one starts, so `while c { } x = 1` on one line is
  rejected.
- The `{` that opens a block must be on the same line as the header or condition before it.
  This holds for a function, `init`, arm, `recv`, `msg`, `contract` and event `struct` header,
  and for the condition of an `if` or `while`. `else` must be on the same line as the `}`
  before it.
- A line that starts with `{` may not follow a statement that ends with a name. Fe can read
  the two as a record literal of that name. So `let a: u256 = x` followed by `{ a }` is
  rejected with `8-0006` **[✓]**. Fe0 rejects it with `P012`. Fe0's rule is wider than Fe's.
  Fe accepts `1 + x` at the end of the line, and Fe0 rejects it. Both accept `(x)` and
  `x + 1` there.

So an expression may span lines only where the innermost open bracket is `(`, and only after
`(`, `,` or a binary operator, or before `)`. Fe's rule is more permissive in some places, for
example a line inside parentheses may start with `||`, so this is a valid subset. Fe also
accepts a line inside parentheses that starts with a binary `+`, and Fe0 rejects it (`L009`)
**[✓]**. The probe is `corpus/reject/line_break_plus.fe`.

Probed **[✓]**:
- Fe accepts a parenthesised expression spread over several lines.
- Fe also reads `let x = a` followed by `(a)` on the next line as two statements, not as the
  call `a(a)`, just as Fe0 does.
- Fe rejects a newline inside the `[ ]` of `m[k]` (`1-0001`), as Fe0 does. The probe is
  `corpus/reject/map_index_newline.fe`.
- Fe reads a newline inside a `{ … }` block in parentheses as Fe0 does. The probe
  `corpus/reject/newline_block_in_parens_call.fe` puts `g` and `(1)` on two lines of such a
  block. Fe accepts it and reads them as the two statements `g` and `(1)`, not as the call
  `g(1)`. The probe `corpus/reject/newline_block_in_parens_return.fe` puts `return` and `5`
  on two lines of such a block. Fe rejects it with `8-0013`. Fe0 rejects both probes, because
  `g` is not a value and that `return` has no value.
- Fe accepts the `{` of an `if` or `while` on the next line.
- Inside parentheses, Fe reads a line that starts with `-` or `*` as a new expression, not as
  the rest of the one before, so it rejects it (`1-0001`). It also rejects a line break before
  or after the `:` of a call label, after `!` or `~`, and between a function's name and the `(`
  of its call. In an `if` condition, Fe ends the condition at a line break before `<`. The
  probes are the other `corpus/reject/line_break_*.fe`. Fe0 rejects them all with `L009`.
- `tools/newline_check.py` compares how Fe and Fe0 split programs into statements, with Fe's
  own parser. It checks the corpus, the reject programs that Fe0 parses, and generated
  programs, each also with random line breaks wherever the rule above allows one. Fe and Fe0
  split all of them the same way.

## 4. Expression semantics

**Evaluation order.**
- Operands and call arguments are evaluated left to right, each exactly once **[✓]**. With
  `z = 0`, both `1 / z + (z - 1)` and `pair(1 / z, z - 1)` revert with `Panic(0x12)` (the left
  operand), not `0x11`.
- In `m[k] = e` and `m[k] op= e`, `e` is evaluated before `k` **[✓]**. So with `z = 0`,
  `m[1 / z] = z - 1` reverts with `Panic(0x11)`, from `z - 1`. The probe is the arm `Order` of
  `corpus/maps.fe`.
- In `p op= e`, `e` is evaluated before the old value of `p` is read **[✓]**. A call in `e`
  may call back into the contract and write `p`. So with `v = 10`, `v += a.call(…)` leaves
  `v` at 101 when the call sets `v` to 100 and returns 1. The probe is
  `corpus/reenter_order.fe`.
- In `log.emit(E { … })`, the values are evaluated in the order written, not in the order of
  the event's fields **[✓]**. The probe is the arm `Order` of `corpus/events.fe`.
- In `a.call(M::V { … })`, `a` is evaluated first, then the values in the order written **[✓]**.
  The probe is the arm `Order` of `corpus/calls.fe`.
- `&&` and `||` short-circuit.

**Arithmetic on `u256`** is checked. Probed failure behaviour:

| Operation | On failure |
|---|---|
| `+` overflow, `-` underflow, `*` overflow | Revert with `Panic(0x11)` **[✓]** |
| `/` or `%` by zero | Revert with `Panic(0x12)` **[✓]** |
| `&` `\|` `^` `~` | Never fail |
| `<<`, `>>` | Never fail. Bits shifted out are discarded (`3 << 255` = 2²⁵⁵), and a shift by 256 or more gives 0, as with the EVM's `SHL`/`SHR` **[✓]** |

- `/` rounds down, and `%` gives the remainder of that division.
- `Panic(c)` means the revert data `0x4e487b71 ‖ uint256(c)`, Solidity's encoding.
- Compound assignment `p op= e` stores `p op e` in the place `p`, with the same checks.
- A revert undoes every storage write and log of the call, as the EVM does.

**Loops.** `while c { … }` runs its body while `c` is true. `break` leaves the innermost loop,
and `continue` goes on to its next test of `c`. Both may stand only inside a loop (`N013`). Fe
rejects them outside one (`8-0019`) **[✓]**. The probe is `corpus/reject/break_outside_loop.fe`.
A `while` has no value.

**Comparisons** are unsigned on `u256`. On `Address`, only equality is allowed.

**`if`.** `if c { a } else { b }` is an expression when both branches produce values of the same
type. Without `else`, it has unit type and may only be used as a statement.

**Blocks.**
- A block's value is its final expression, if there is one.
- A function or arm body's final expression is its return value.

**`assert!(c)`** reverts with `Panic(0x01)` when `c` is false **[✓]**.

**`assert!(c, "msg")`** reverts with `Error(string)` instead **[✓]**: `0x08c379a0` followed by
the ABI-encoded string. A message of any length is encoded whole **[✓]**. The probe is
`corpus/messages.fe`.

## 5. Names, scopes and checking

1. **Items** (`const`, `fn`, `msg`, `contract` and events) form one namespace and may be
   declared in any order. Duplicates are an error (`N001`). Fe rejects an event named like a
   msg (`2-0004`) **[✓]**.
   - Two parameters of a function, two variants of a msg, and two fields of a variant or of an
     event may not share a name either (`N001`). Fe rejects each of these **[✓]**. The probes
     are `corpus/reject/duplicate_param.fe`, `duplicate_variant.fe` and `duplicate_field.fe`.
2. **Locals.** `let`, `var` and the binds of a `recv` arm declare locals.
   - `let` declares an immutable local and `var` a mutable one. Assigning to a `let` local or
     to a parameter is an error (`N014`), as in Fe (`8-0018`) **[✓]**. The probes are
     `corpus/reject/assign_let.fe` and `corpus/reject/assign_param.fe`.
   - Shadowing with a new `let`/`var` is allowed **[✓]**.
   - A local's scope runs from after its declaration to the end of its block.
   - A local hides a storage field, an effect or an item of its name until the end of its block,
     and a parameter or a bind hides it in the whole body. So `g()` after `let g` is not a call
     (`N004`). Fe does the same (`8-0021`) **[✓]**. The probes are `corpus/shadowing.fe` and
     `corpus/reject/local_shadows_fn.fe`.
   - The name of a parameter or a bind may not be the name of an entry of its body's `uses`
     (`N005`). Fe rejects it too (`8-0134`) **[✓]**. The probes are
     `corpus/reject/param_named_like_use.fe` and `bind_named_like_use.fe`.
   - The name of a local may not be the name of a constant, the contract or an event (`N018`).
     Fe reads such a name as a pattern and rejects it. It rejects a constant as refutable
     (`8-0101`, and `8-0153` for a bind), the contract as a type mismatch (`8-0000`), and an
     event as a pattern with too few fields (`8-0004`) **[✓]**. The probes are the
     `corpus/reject/shadow_item_*.fe` programs.
   - The name of a local may not start with an uppercase letter (`N017`).
   - Fe rejects fewer uppercase locals than Fe0. Fe reads an uppercase local or bind that names
     a type or a variant in scope, such as `let Some` or `x: Option`, as a pattern, and rejects
     it **[✓]**. It accepts any other uppercase local, such as `let Foo` **[✓]**. The probe is
     `corpus/reject/uppercase_let_not_a_type.fe`. Fe0 uses the stricter rule for locals
     ([ADR 0001](adr/0001-strict-subset.md)).
   - Fe accepts every uppercase parameter, even `_ Option: u256` **[✓]**, and so does Fe0. The
     probe is `corpus/uppercase_params.fe`.
3. **Constants** are evaluated at compile time with the §4 semantics. Overflow is a compile-time
   error (`3-0034`), and so is division by zero (`3-0025`) **[✓]**.
   - A constant expression is built from integer and `bool` literals, other constants, the
     operators of §4 and parentheses. Anything else is `C001`.
   - So a map entry is not a constant expression. Fe rejects one too, because the map is an
     undefined name there (`8-0012`) **[✓]**. The probe is `corpus/reject/map_in_const.fe`.
   - Fe accepts an `if` in a constant **[✓]**, and Fe0 rejects it. The probe is
     `corpus/reject/if_in_const.fe`.
   - A constant may refer to a later one, as in Fe **[✓]**. A constant whose value depends on a
     cycle of constants is `N006`. Fe rejects it too (`3-0037`) **[✓]**. The probes are
     `corpus/consts.fe` and `corpus/reject/const_cycle.fe`.
4. **Function calls.**
   - A parameter written `_ x: T` is positional: call it as `f(e)`.
   - A parameter written `x: T` is labelled: call it as `f(x: e)`, or as `f(x)` when the
     argument is the identifier `x` itself **[✓]**. Leaving out a required label is `8-0024`
     **[✓]**.
   - Arguments must follow the parameter order. Swapped labels are `8-0024` **[✓]**.
   - Recursion is allowed. Fe0 adds no limit beyond EVM gas and stack depth.
   - A function is not a value (`N003`). Fe accepts `let h = g` **[✓]**. The probe is
     `corpus/reject/fn_as_value.fe`.
5. **Free functions are pure.** They have no `uses` clause, so they cannot touch storage, read
   the caller, emit an event or call a contract (§6). Fe rejects a free function that reads
   the caller or a map, because `ctx` or the map is an undefined name there (`8-0012`)
   **[✓]**. The probes are `corpus/reject/ctx_in_free_function.fe` and
   `corpus/reject/map_in_free_function.fe`.
6. **Return paths.** A function with `-> T` must produce a `T` on every path, either through its
   final expression or through `return`. Otherwise it is an error (`T001`), as in Fe
   (`8-0000`, type mismatch) **[✓]**.
   - A `while` never counts as a path that leaves, even `while true`. So
     `fn f() -> u256 { while true { return 1 } }` is an error (`T001`). Fe accepts it **[✓]**.
     The probe is `corpus/reject/while_true_tail.fe`.
7. **A tail after a diverging statement.** A block with a final expression has that
   expression's type, even when `return`, `break` or `continue` comes before it and the
   expression is never reached. A block without a final expression has unit type. When one
   of its statements diverges, the block diverges too, and then it fits any type.
   - Fe rejects `return 1` followed by `true` in a function `-> u256` (`8-0000`) **[✓]**. The
     probe is `corpus/reject/never_tail_return.fe`.
   - Fe rejects `break` followed by `5` in a loop body (`8-0031`) **[✓]**. The probe is
     `corpus/reject/never_tail_break.fe`.
   - Fe accepts `return 1` followed by `2` in a function `-> u256`, and so does Fe0 **[✓]**.
     The probe is `corpus/one_line.fe`.

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
  counted** **[✓]**. Fe packs them as Solidity does (#1826):
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
- For when immutables are added: a field declared without `mut` is read-only after `init`
  **[✓]**.
  - `init` may still write it, with `uses (mut v)`.
  - An arm that declares `mut v` on it is rejected (`8-0085`).

**Effects (`uses`).** Every `init` and arm body is checked:
- Reading field `f` requires `f` or `mut f` in its `uses`. Otherwise it is an error, as in Fe
  (`8-0116`) **[✓]**.
- Assigning to `f` requires `mut f` (`8-0018`) **[✓]**.
- Listing a field the contract doesn't have is an error (`8-0051`) **[✓]**.
- Fe accepts *unused* `uses` entries **[✓]**, so Fe0 reports them only as warnings.
- A field listed twice, as in `uses (v, mut v)`, is an error (`N001` at the second entry). Fe
  rejects it too (`3-0093`) **[✓]**. The probe is `corpus/reject/uses_twice.fe`.

This check is the point of Fe0.

**The caller** ([ADR 0017](adr/0017-caller.md)). A contract may declare `Ctx` effects, as in
`contract Owned uses (ctx: Ctx) {`. `init` and arms grant a `Ctx` effect in their `uses` as they
grant a storage field.
- `ctx.caller()` is the address that called the contract. In `init`, it is the address that
  deploys the contract. A body that reads it must list `ctx` in its `uses`, as for a storage
  field (`E116`). Fe rejects such a body too, because `ctx` is an undefined name there
  (`8-0012`) **[✓]**.
- `ctx.address()` is the address of the contract itself, which a pool needs to ask a token for
  its own balance ([ADR 0020](adr/0020-external-calls.md)). In `init`, it is the
  address of the contract being created. It needs `ctx` in the body's `uses` as
  `ctx.caller()` does, and Fe rejects a body without it the same way (`8-0012`) **[✓]**. Fe
  accepts `log.address()` on a `Log` effect **[✓]**, and Fe0 rejects it (`T001`).
- Nine more methods of `Ctx` each read one value of the transaction or the block, with one EVM
  instruction in Fe and in Fe0. `ctx.origin()` and `ctx.coinbase()` give an `Address`.
  `ctx.gasprice()`, `ctx.block_number()`, `ctx.prevrandao()`, `ctx.gaslimit()`,
  `ctx.chainid()`, `ctx.basefee()` and `ctx.blobbasefee()` give a `u256` **[✓]**. Each needs
  `ctx` in the body's `uses`, as `ctx.caller()` does. The probe is `corpus/ctx_methods.fe`.
- `Address::zero()` is the address 0. It needs no effect, so a free function may use it. It is
  not a constant expression (`C001`). Fe rejects it in a constant too, because `zero` is not a
  `const fn` (`3-0024`) **[✓]**.
- A `Ctx` effect is not a value. A name that refers to one is an error (`N003`), except before
  one of its methods. Assigning to one is an error (`N014`), even when `uses` names it `mut`. Fe
  rejects both **[✓]**.
- A `Ctx` effect takes no storage. The storage fields' slots are the same as without it.
- A storage field may not take the name of an effect (`N001`). For a `Ctx` effect, Fe rejects
  such a storage field **[✓]**.
- A local, a parameter or a bind named like an effect follows the rules of §5.2. Fe accepts a
  local named like a `Ctx` effect **[✓]**. The probe is `corpus/shadowing.fe`.
- A `Ctx` effect may be written `mut Ctx`, and it means the same as `Ctx`, as in Fe **[✓]**.
  The probe is `corpus/two_effects.fe`.
- The same effect name declared twice is an error (`N001`). Fe rejects it too (`3-0093`)
  **[✓]**. The probe is `corpus/reject/ctx_duplicate_effect.fe`.
- Only a `Ctx` effect has the methods above (`T001`). Fe rejects `owner.caller()` on an
  `Address` field too, because `Address` has no such method (`2-0010`) **[✓]**. The probe is
  `corpus/reject/ctx_not_an_effect.fe`.
- Fe0 takes the methods of Fe's `Ctx` that take no arguments and return `u256` or `Address`,
  except `gas()` ([ADR 0017](adr/0017-caller.md)). `timestamp()`, `value()` and
  `selfbalance()` return types that Fe0 lacks. Fe0 also leaves out the methods that take
  arguments, such as `balance(a)` and `blockhash(n)`. Fe accepts
  `ctx.gas()` and `ctx.blockhash(1)` **[✓]**.
- Fe0 rejects a method without arguments that it leaves out or that `Ctx` lacks (`N002`). The
  probes are `corpus/reject/ctx_other_method.fe` and `corpus/reject/ctx_unknown_method.fe`.
  Fe0's parser rejects a method call with arguments at its first argument (`P002`). The probe
  is `corpus/reject/ctx_method_args.fe`.

**Maps** ([ADR 0018](adr/0018-storage-maps.md)). A contract field may be a map, as in
`mut balances: StorageMap<Address, u256>`. Its key type and its value type are each `u256`,
`bool` or `Address`.
- `m[k]` is the entry of map `m` at key `k`, and it has the map's value type. An entry that was
  never written reads as zero: `0`, `false` or the address 0.
- `m[k] = v` writes the entry.
- `m` must be a map, `k` must have the key type, and `v` must have the value type (`T001`).
  Fe rejects indexing a field that is not a map (`8-0016`), and a key or value of another type
  (`8-0000`) **[✓]**. The probes are `corpus/reject/map_index_not_a_map.fe`,
  `corpus/reject/map_key_type.fe` and `corpus/reject/map_value_type.fe`.
- `m[k] op= v` needs a `u256` entry (`T001`), as any compound assignment does (§4). Fe rejects
  `f[k] += true` on a `bool` entry (`8-0016`) **[✓]**. The probe is
  `corpus/reject/map_compound_bool.fe`.
- Reading an entry needs `m` in the body's `uses`, and writing one needs `mut m`, as for a
  storage field (`E116`, `E018`). Fe rejects both **[✓]**.
- A map is not a value (`N003`), and a whole map is not assignable (`N014`). Fe rejects the
  assignment (`16-0010`) **[✓]**, and accepts `let y = m` **[✓]**.
- Only a contract field may have a map type (`P004`). Fe also accepts a map as a parameter, and
  maps of maps **[✓]**.
- A map field must be `mut`, as every field must (`P010`). Fe rejects a map field without
  `mut` too, because a map lives only in storage (`3-0061`) **[✓]**.

Storage. Fe lays maps out as Solidity does **[✓]**:
- A map takes a slot of its own, so the field before it ends its slot and the field after it
  starts the next one. Nothing is ever written to that slot.
- The entry at key `k` lives in slot `keccak256(k ‖ s)`, where `s` is the map's slot and both
  are 32-byte words. A `bool` key is the word 0 or 1, and an `Address` key is its 20 bytes,
  zero-extended. Each entry has its slot to itself, and its value is stored as the whole word.

The probe is `corpus/maps.fe`, which also runs on a node (DESIGN.md §10, "On a node").

**Events** ([ADR 0019](adr/0019-events.md)). An event is a struct marked `#[event]`. Its
fields are `u256`, `bool` or `Address`, and each may be marked `#[indexed]`:

```fe
#[event]
struct Transfer {
    #[indexed]
    from: Address,
    #[indexed]
    to: Address,
    value: u256,
}
```

A contract emits events through a `Log` effect declared `mut`, as in
`contract Token uses (ctx: Ctx, log: mut Log) {`.
- `log.emit(E { f: e, … })` emits event `E`. `{ f }` stands for `{ f: f }`, and the fields may
  be written in any order.
- Only an event can be emitted (`T001`). Fe rejects emitting a msg too **[✓]**. A name that
  nothing declares is `N002`.
- Each field of `E` gets one value of its type. A value that names no field of `E` is `N010`. A
  field given twice is `N001`. A field left out is `N019`. A value of another type is `T001`.
  Fe rejects each of these errors too **[✓]**.
- Emitting needs `log` in the body's `uses` (`E116`), with or without `mut`. Fe rejects a body
  that does not list `log` (`8-0012`) **[✓]**, and accepts `uses (log)` **[✓]**. The probe is
  `corpus/events.fe`.
- `log.emit(…)` has no value (`T003`). Fe accepts `let x = log.emit(…)` **[✓]**.
- An event has at most three indexed fields (`T006`). Fe rejects four (`10-0006`) **[✓]**.
- An event is not a value (`N003`), and neither is a `Log` effect. Fe rejects `log` as a value
  (`16-0002`) **[✓]**.
- A `Log` effect has no `caller()` (`T001`). Fe accepts `log.caller()` **[✓]**.
- A `Log` effect may be declared without `mut`, as `log: Log`, but then no body may emit
  through it (`E004`), even when its `uses` grants it `mut`. Fe accepts the declaration and
  rejects the emit (`8-0066`) **[✓]**. A contract may have several `Log` effects. Like `Ctx`
  effects, they take no storage.

The log. `log.emit(E { … })` emits `LOGn` with `n` one more than the number of indexed
fields **[✓]**:
- Topic 0 is `keccak256` of the event's signature: its name, then the types of all its fields
  in declaration order, as `uint256`, `bool` and `address`, in parentheses and separated by
  commas. The `Transfer` above has the signature `Transfer(address,address,uint256)`.
- The indexed fields follow as topics, in declaration order. A `bool` is the word 0 or 1, and
  an `Address` its 20 bytes, zero-extended.
- The data is the other fields as ABI words, in declaration order. An event with no data
  fields logs no data.

The probe is `corpus/events.fe`, which runs on a node (DESIGN.md §10, "On a node").

**Calls** ([ADR 0020](adr/0020-external-calls.md)). A contract calls another contract through a
`Call` effect declared `mut`, as in `contract Pool uses (call: mut Call) {`. The call sends a
variant of a msg that the program declares, often the other contract's msg written out again:

```fe
msg Erc20 {
    #[selector = 0xa9059cbb]
    Transfer { to: Address, amount: u256 } -> bool,
}

// in a body whose uses has `call`:
let ok = token.call(Erc20::Transfer { to, amount })
```

- `a.call(M::V { f: e, … })` calls the contract at address `a`, which is a name of type
  `Address`: a local, a parameter or a field (`T001`). Its value has the variant's return
  type, and a variant without one gives a call with no value (`T003`). Fe accepts `let x =`
  such a call **[✓]**.
- `M` must name a msg (`N002`, `N007`) and `V` one of its variants (`N008`). The values follow
  the rules of `log.emit` (§6, "Events"): `N010`, `N001`, `N019` and `T001`, which Fe rejects
  too **[✓]**. The variant is written with braces, even when it has no fields. Fe rejects
  `M::V` without them when `V` has a return type **[✓]**.
- A body that calls needs the contract's `Call` effect, whatever its name, in its `uses`
  (`E116`), with or without `mut`. Fe rejects a body without the effect (`8-0036`) **[✓]**,
  and accepts `uses (call)` **[✓]**. The probe is `corpus/calls.fe`.
- A contract has at most one `Call` effect (`N001` at the second). Fe rejects a body that
  grants two (`8-0040`) and accepts a contract that declares two when no body grants both
  **[✓]**.
- A `Call` effect may be declared without `mut`, as `call: Call`, but then no body may call
  (`E004`), even when its `uses` grants the effect `mut`. Fe accepts the declaration and
  rejects the call (`8-0037`) **[✓]**.
- A `Call` effect is not a value (`N003`) and has no `caller()` (`T001`). Fe accepts
  `call.caller()` **[✓]**. Like the other effects, it takes no storage.

The call. Fe0 does what Fe's `Address::call` does, and the probe `corpus/calls.fe` checks each
point on a node against `corpus/callee.fe` **[✓]**:
- The calldata is the variant's selector, then the values as ABI words in the order of the
  variant's fields, as a `recv` arm reads them. A `bool` is the word 0 or 1, and an `Address`
  its 20 bytes, zero-extended.
- `CALL` forwards all the gas the EVM allows, which is all but a 64th, and sends no value.
- When the callee fails, the call reverts with the callee's revert data, unchanged. So a
  callee's `Panic` or `Error(string)` reaches the caller's caller.
- When the callee succeeds, a variant with a return type takes the first word of the return
  data and ignores the rest. Fewer than 32 bytes, a `bool` word other than 0 or 1, or an
  `Address` word with any of its upper 96 bits set: the call reverts with empty data. A variant
  without a return type ignores the return data.
- An address with no code succeeds with no return data. So a call of a variant without a
  return type to such an address succeeds, and one with a return type reverts with empty
  data. Fe0, like Fe, does not check the code size first.
- The callee may call back into the caller before it returns, and sees the storage the caller
  wrote before the call. Fe0 has no guard against that, as Fe has none
  ([ADR 0020](adr/0020-external-calls.md), "Consequences").

**Messages and dispatch.**
- In `recv M`, `M` must name a msg (`N002`, `N007`) **[✓]**.
- A `recv M` block must have exactly one arm per variant of `M` **[✓]** (the "missing variants"
  error).
- A contract has at most one `recv` block for a msg (`N001`). Fe rejects a second
  (`8-0046`) **[✓]**. The probe is `corpus/reject/recv_twice.fe`.
- Arm bindings name the variant's fields: `Set { a: x }` binds field `a` to the local `x`, and
  `Set { a }` binds it to the local `a`.
- An arm binds every field of its variant (`N011`), and each one once (`N001`). Fe rejects a
  field left out (`8-0011`) and a field bound twice (`8-0008`) **[✓]**. The probes are
  `corpus/reject/arm_missing_field.fe` and `corpus/reject/duplicate_bind.fe`.
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
- A program declares exactly one contract: `G001` without one and `N015` at a second. Fe
  accepts a module with none or with several **[✓]**, so this rule is Fe0's own. The probes
  are `corpus/reject/no_contract.fe` and `corpus/reject/two_contracts.fe`.

## 7. Diagnostics

- Fe0 stops at the first error. Warnings (unused `uses` entries) do not stop it.
- It reports `line:col`, a stable error code (`L` lexical, `P` parse, `N` name, `T` type, `E`
  effect, `C` const-eval, `G` generation) and a one-line message.
- Error codes are part of the test suite. Matching Fe's message wording is not a goal.

## 8. Conformance testing

The subset rule is tested three ways.

- **Accepted programs.** A differential test compiles one source with Fe and with Fe0, the
  latter running on the EVM, and deploys both builds with the same constructor arguments and
  value. Either both deployments create a contract or neither does. Then both contracts get
  the same calls, and each call must give the same success flag and the same return or
  revert data, byte for byte. Inside `fe test`, storage effects show through the later calls
  that read them. On a node, the logs and the storage writes of each call must match too
  (DESIGN.md §10, "On a node").
- **Rejected programs.** Fe0 must give the expected error code at the expected position, and
  Fe must reject the program too, unless the rule is one that Fe0 adds on top of Fe (such as
  §5.3's ban on `if` in a constant). Then Fe must accept it.
- **Changed programs.** Accepted programs are changed by one mutation each. Fe0 and Fe must
  then agree on whether each changed program is valid, unless the rule by which Fe0 rejects it
  is one of the rules above that Fe0 adds on top of Fe (DESIGN.md §11a).

The aim is a test of one of these kinds for every rule above that has a [✓] mark. The tests are
in `corpus/`, `corpus/reject/` and `fe0/src/codegen_tests.fe`, and DESIGN.md §10 describes how
the harness runs them. `tools/mutate.py` makes the changed programs (DESIGN.md §11a).

## 9. Open questions

No question is open. Each answer is in the section that owns its rule.

## 10. Fe0 and Fe at a glance

A summary of the sections above, for a reader who wants the shape of the subset before its
rules. Each row points to the section that owns the rule; where the two disagree, that section
wins. ✅ means Fe0 has the feature as Fe does. ◐ means Fe0 has it with a narrower rule, so it
rejects some programs that Fe accepts. ❌ means Fe0 leaves it out, though it is valid Fe (§3.3).

**Types**

| Feature | Fe0 | Where |
|---|---|---|
| `u256`, `bool`, `Address`, with checked arithmetic | ✅ | §2, §4 |
| Other integer widths, signed integers, `usize`, `isize` | ❌ | §2 |
| `String` | ◐ only as an `assert!` message | §1 |
| Tuples, arrays, structs other than events, enums, references | ❌ | §2, §3.3 |
| Generics, traits, `impl`, closures, `as` casts | ❌ | §3.3 |
| A literal's type inferred from later uses | ◐ the type must be fixed where the literal is written | §2 |

**Syntax and expressions**

| Feature | Fe0 | Where |
|---|---|---|
| Binary operators and their precedence | ✅ | §3.2 |
| Unary `+` | ◐ not at the start of a line where a newline can end a statement | §3.2, §3.4 |
| `!` on `u256`, `& \| ^` on `bool` | ❌ | §2 |
| A unit value, as in `let x = g()` | ❌ | §2 |
| `while true` as a path that leaves a function | ❌ | §5.6 |
| `**` | ❌ | §3.3 |
| Compound assignment | ✅ | §1 |
| Decimal, hex, octal and binary literals | ✅ | §1 |
| `if` as an expression, block values | ✅ | §4 |
| `while`, `break`, `continue`, `return` | ✅ | §3.1 |
| `for`, ranges, `loop`, `match` | ❌ | §3.3 |
| `let`, `var`, shadowing | ✅ | §5.2 |
| Field access and method calls | ❌ except the `Ctx` methods of §6, `log.emit`, `a.call` | §3.3 |
| Line breaks inside an expression | ◐ only inside `( )`, after `(`, `,` or an operator, or before `)` | §3.4 |
| A `<` that may open generic arguments | ◐ rejected whenever it may | §3.2 |
| Doc comments | ✅ | §1 |

**Items and names**

| Feature | Fe0 | Where |
|---|---|---|
| `const` | ◐ literals, other constants and operators only | §5.3 |
| Functions with positional and labelled parameters | ✅ | §5.4 |
| Recursion | ◐ deeper than Fe's stack limit, Fe0 differs | the subset rule, §5.4 |
| `mod`, `use`, `extern`, `unsafe`, `with` blocks | ❌ | §3.3 |
| A local or a parameter named like a field or an item | ✅ | §5.2 |
| Uppercase parameters | ✅ | §5.2 |
| Uppercase locals | ◐ rejected | §5.2 |
| Type names as names | ◐ rejected everywhere | §1 |
| `init`, `recv`, `assert` and `with` as names | ✅ | §1 |
| A program without exactly one contract | ◐ rejected | §6 |
| A function as a value | ❌ | §5.4 |

**Contracts and effects**

| Feature | Fe0 | Where |
|---|---|---|
| `msg` with literal selectors, `recv` with one arm per variant | ✅ | §6 |
| `sol("…")` selectors | ❌ a stretch goal | §3.3 |
| Fallback arms, `#[payable]` | ❌ | §3.3 |
| `mut` storage fields, with Fe's packing | ✅ | §6 |
| Fields without `mut` | ❌ a stretch goal | §6 |
| `StorageMap` of `u256`, `bool` and `Address` | ✅ | §6 |
| Maps elsewhere, maps of maps, `StorageMap` methods | ❌ | §3.3 |
| `uses` checks on `init` and arms | ✅ | §6 |
| `mut Ctx` | ✅ | §6 |
| `Log` and `Call` granted without `mut` | ✅ | §6 |
| `Log` and `Call` declared without `mut` | ✅ | §6 |
| `uses` on free functions | ❌ free functions are pure | §5.5 |
| `Ctx` methods without arguments that return `u256` or `Address`, except `gas()` | ✅ | §6 |
| `gas()`, the `Ctx` methods that return `Wei` or `Timestamp`, and those with arguments | ❌ | §6 |
| Events with up to three indexed fields of the three types | ✅ | §6 |
| `a.call(M::V { … })` | ✅ | §6 |
| `try_call`, static calls, gas or value on a call | ❌ | §3.3 |
| The dispatcher, ABI decoding and `init` arguments | ✅ | §6 |
| Diagnostics | ◐ the first error only, as a stable code | §7 |
