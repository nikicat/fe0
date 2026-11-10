#!/usr/bin/env bash
# Re-run every pre-window spike/probe against a Fe binary and compare with the values
# recorded in docs/adr/, SPEC.md and DESIGN.md. Usage: tools/spikes.sh [path/to/fe]
# Many probe tests fail on purpose to report a value via Panic(code); we compare that code.
set -u
FE=${1:-fe}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
fails=0

# panic code reported by a single test (hex, without 0x), or the first line of its failure
code() { # dir test [extra fe test args...]
    local dir=$1 t=$2; shift 2
    (cd "$ROOT/$dir" && "$FE" test --filter "$t" "$@" 2>&1) |
        grep -oE '0x4e487b71[0-9a-f]+|Test halted: [A-Za-z(]+' | head -1 | sed -E 's/^0x4e487b71//'
}

check() { # label actual expected
    if [ "$2" = "$3" ]; then printf 'ok    %-34s %s\n' "$1" "$2"
    else printf 'DIFF  %-34s got %s, expected %s\n' "$1" "$2" "$3"; fails=$((fails + 1)); fi
}

hexword() { printf '%064x' "$1"; }

echo "fe: $("$FE" --version)"

# spike-lexer: plain tests pass; gas for lexing 1 KB; create_raw and Bytes-split checks
for t in lexes_a_small_function create_raw_then_call create_raw_bad_initcode_gives_zero_address \
         bytes_through_one_contract bytes_through_facade; do
    r=$(cd "$ROOT/spike-lexer" && "$FE" test --filter "$t" 2>&1 | grep -cE "PASS .* $t$")
    check "spike-lexer $t" "$r" 1
done
# gas drifts with every compiler update, so allow +-5% around the recorded 802,865
g=$((16#$(code spike-lexer lex_gas -O 1)))
check "lexer gas per KB (-O1) within 5%" "$(( g * 100 / 802865 >= 95 && g * 100 / 802865 <= 105 ))" 1
echo "      (lexer gas per KB: $g)"

# spike-layout: storage/revert payloads
check "revert: overflow"      "$(code spike-layout rev_overflow)"      "$(hexword 0x11)"
check "revert: underflow"     "$(code spike-layout rev_underflow)"     "$(hexword 0x11)"
check "revert: div by zero"   "$(code spike-layout rev_divzero)"       "$(hexword 0x12)"
check "revert: assert"        "$(code spike-layout rev_assert)"        "$(hexword 0x01)"
check "revert: unknown sel"   "$(code spike-layout rev_unknown_selector)" "$(hexword 0x100)"

# spike-conform runtime probes: (success<<100 | len<<64 | head<<32 | tail)
pp() { python3 -c "print(f'{($1<<100)|($2<<64)|($3<<32)|$4:064x}')"; }
check "mul overflow"        "$(code spike-conform r_mul_overflow)"  "$(pp 0 36 0x4e487b71 0x11)"
check "mod by zero"         "$(code spike-conform r_mod_zero)"      "$(pp 0 36 0x4e487b71 0x12)"
check "shl 256 -> 0"        "$(code spike-conform r_shl_256)"       "$(pp 1 32 0 0)"
check "shl 255 discards"    "$(code spike-conform r_shl_255)"       "$(pp 1 32 0x80000000 0)"
check "eval order binary"   "$(code spike-conform r_order_bin)"     "$(pp 0 36 0x4e487b71 0x12)"
check "eval order args"     "$(code spike-conform r_order_args)"    "$(pp 0 36 0x4e487b71 0x12)"
check "calldata bool=2"     "$(code spike-conform d_bool_2)"        "$(pp 0 0 0 0)"
check "calldata dirty addr" "$(code spike-conform d_addr_highbits)" "$(pp 0 0 0 0)"
check "calldata short"      "$(code spike-conform d_short_args)"    "$(pp 0 0 0 0)"
check "calldata extra bytes" "$(code spike-conform d_extra_bytes)"  "$(pp 1 32 0 3)"
check "value to nonpayable" "$(code spike-conform d_value_nonpayable)" "$(pp 0 0 0 0)"
check "init valid"          "$(code spike-conform init_valid)"      "$(hexword 1)"
check "init bool=2"         "$(code spike-conform init_bool_2)"     "$(hexword 0)"
check "init with value"     "$(code spike-conform init_with_value)" "$(hexword 0)"

# spike-limits
check "recursion depth"     "$(code spike-limits recursion_depth)"  "$(hexword 1019)"
check "fe test EIP-170"     "$(code spike-limits contract_size_limit)" "$(hexword 0x111)"

# spike-deps: duplicate contract names (argotorg/fe#1887) — expect the crash until fixed
r=$(cd "$ROOT/spike-deps/user" && "$FE" test 2>&1 | grep -c 'test result: ok')
check "path dependency"     "$r" 1

# spike-keccak: one round, EVM vs native vs Python reference
check "keccak round (EVM)"  "$(code spike-keccak keccak_round_evm)" "$(printf '%064x' 0x01ac8e14a6e6ea79)"
(cd "$ROOT/spike-keccak" && "$FE" build --backend native >/dev/null 2>&1)
check "keccak round (native)" "$("$ROOT/spike-keccak/out/spike_keccak" 2>&1)" "01ac8e14a6e6ea79"

# spike-lexer native: same token stream as recorded
(cd "$ROOT/spike-lexer" && "$FE" build --backend native >/dev/null 2>&1)
check "lexer (native)" "$(printf 'fn f(x) -> u8 { x == 42 }' | "$ROOT/spike-lexer/out/spike_lexer" | tr '\n' ';')" \
    "1 0 2;0 3 1;3 4 1;0 5 1;3 6 1;3 8 2;0 11 2;3 14 1;0 16 1;3 18 2;2 21 2;3 24 1;4 25 0;"

# spike-native/probe_stderr: stderr through libc's `write`, which 26.5.1's std::io lacks
"$FE" build --backend native -e executable --out-dir "$ROOT/out/spikes" \
    "$ROOT/spike-native/probe_stderr.fe" >/dev/null 2>&1
r=$("$ROOT/out/spikes/probe_stderr" 2>&1 >/dev/null; echo "exit $?")
check "stderr (native)" "$(echo "$r" | tr '\n' ';')" "oops!;exit 3;"

# compile-time probes: accept/reject as recorded in spike-conform/compile
for f in "$ROOT"/spike-conform/compile/*.fe; do
    n=$(basename "$f" .fe)
    if "$FE" check --standalone "$f" 2>&1 | grep -qE '^error'; then got=REJECT; else got=ACCEPT; fi
    case $n in
        assign_let|chain_cmp|const_divzero|const_overflow|field_nonmut_arm_write|label_required|\
        label_wrong_order|no_return_path|selector_dup_across_msgs|selector_dup_in_msg|\
        selector_too_large|uses_missing_read|uses_ro_write|uses_unknown_field) want=REJECT ;;
        *) want=ACCEPT ;;
    esac
    check "compile: $n" "$got" "$want"
done

echo "---"; [ $fails -eq 0 ] && echo "all recorded values reproduced" || echo "$fails difference(s)"
exit $((fails > 0))
