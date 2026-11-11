---
status: todo
tags: [upstream]
---
# Watch Fe master

## Goal
Notice upstream changes that affect us, without a second upgrade mid-window (ADR 0015,
PLAN.md risks 1–2).

## State
Nov 11: we moved to the release 26.6.0 (ADR 0015, T324k1). It holds everything that the last
check found on master, including the removal of character I/O and the owning `DynString`.
Master after `5b3f96af2` (the 26.6.0 release commit) has not been built yet.

## Next
Every couple of days: rebuild master, then run the fe0 tests and
`tools/spikes.sh /workspaces/fe-master/target/release/fe`. On an arm64 host, master needs the
`Os::host()` patch for the native probes (WORKAROUNDS.md).
```sh
git -C /workspaces/fe-master fetch --depth 1 origin master && git -C /workspaces/fe-master checkout -B master FETCH_HEAD
(cd /workspaces/fe-master && cargo build --release -p fe --features cranelift)
```
