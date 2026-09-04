# Phase 7 Notes

## Multi-Block Execution

`rtlflow run --all` discovers block directories that contain `block.yaml`.
`--blocks adder,fifo` runs an explicit comma-separated subset. `--jobs 1`
forces serial execution for debugging; higher job counts use process workers and
print each block's output as a unit when that block completes.

## Cache Inputs

The cache key includes the block source file list, each source file's contents,
the block config, the project flow/check config, the selected flow, and captured
tool version strings. This is intentionally conservative: returning a stale pass
is worse than rerunning a block.

The cache lives under `work/cache/`, which is ignored by git. Cache hits are
materialized into a fresh per-block run directory with `cached: true` and stage
statuses marked `CACHED`.

## Baseline Finding Identity

Baseline comparison keys findings by tool, rule ID, file, and a normalized
message. It intentionally does not include line number, because adding a line at
the top of a file should not turn every existing finding into NEW plus FIXED.

The tradeoff is that two identical findings from the same rule in the same file
can collapse into one identity. That is acceptable for the current use case:
the comparison is meant to highlight whether a class of issue is newly present
in a file, not to be a perfect diagnostic database.
