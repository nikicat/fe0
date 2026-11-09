---
status: todo
tags: [upstream]
---
# Watch Fe master

## Goal
Notice upstream changes that affect us, without leaving 26.5.1 mid-window (PLAN.md risks 1–2).

## State
Last checked Nov 8: master `b182b0126` rejects fe0 in three places, listed in WORKAROUNDS.md
("Master makes `DynString`, `Bytes` and `DynArray` own their memory"). Master `95ec05413`
(Nov 4) passed it. origin/master is at `80eaf2deb` (Nov 8) and was not built. VS Code's Fe
extension runs the master build, through `FE_PATH`, so the editor shows these errors and
CI does not.

Merged since Oct 28: #1883 (native portability), #1878 (`--emit sizes`), #1890 (fixes #1887),
#1909 (fixes #1886, native keccak); master also removed `std::io` character I/O. Still open:
#1882 (arithmetic mode at the operator: rerun the spike-conform probes when it lands), #1845
(fieldless msg variants without `{}`: recheck the SPEC example).

## Next
Every couple of days: rebuild master, then run `tools/spikes.sh ~/src/fe/target/release/fe`
and the fe0 tests.
```sh
git -C ~/src/fe fetch --depth 1 origin master && git -C ~/src/fe checkout -B master FETCH_HEAD
(cd ~/src/fe && cargo build --release -p fe --features cranelift)
```
