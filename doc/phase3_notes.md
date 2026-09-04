# Phase 3 Notes

## Why Stage Has One Run Method

Lint did not fit the Phase 2 `Simulator` interface. Simulation had a visible
`build()` and `run()` split, but lint has one subprocess invocation and produces
findings instead of a waveform-oriented pass/fail result. Future stages will
also vary: coverage may have several internal steps, while a custom checker may
only parse source files.

`Stage.run(cfg, ctx)` is therefore the public interface. Each stage owns its
internal steps and returns one `StageResult`. That keeps orchestration simple:
the flow runner only needs to know whether a stage passed, failed, errored, or
was skipped, plus which findings and artifacts it produced.

## What Broke In The Simulator Shape

The old simulator shape assumed:

- every tool has separate build and execute phases
- output is mainly a waveform and log
- failure is equivalent to simulation failure

Lint breaks all three assumptions. It has no waveform, no execute step, and its
normal output is a list of source findings. A linter returning non-zero because
it found warnings is a block `FAIL`, while a missing executable is a stage
`SKIPPED` or `ERROR`. Collapsing those cases makes flow policy impossible to
reason about later.

## Waiver Policy

Waivers require `reason` and `expires`. Expired waivers are not applied and fail
the lint command so temporary exceptions do not silently become permanent.

Stale waivers are detected by matching every active waiver against the current
finding list. If a waiver matches nothing, the original finding may have been
fixed, so `rtlflow waivers --audit` and `rtlflow lint` report it.
