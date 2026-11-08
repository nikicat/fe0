---
status: todo
tags: [tests]
---
# A payload type in difftest.fe

## Goal
`Builds.deploy`, `Builds.deploy_main`, `Deployed.call` and `create` in `fe0/src/difftest.fe`
each take the bytes to send and a value in wei as two parameters. On the Python side,
`fegen.Payload` already holds the two together. Add a Fe `Payload { data, value }` that
mirrors it, and have `tools/fegen.py` emit it. The `case` code stays a parameter, since it
differs at every call. This is test code only, so it costs no compiler bytes.
