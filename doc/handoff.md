# RTL Flow Handoff

## What The Tool Does

`rtlflow` runs lint, project checks, and simulation stages for SystemVerilog
blocks. Runs produce structured `results.json`, optional HTML/JUnit reports,
and reproducibility metadata.

## Add A Block

Create `blocks/<name>/block.yaml` and `files.f`. The YAML needs `name`, `top`,
`sources`, and `timeout_sec`. `parameters` is optional.

For external RTL, run:

```bash
rtlflow adopt path/to/rtl --write-config .rtlflow/adopted/<name>/block.yaml
rtlflow run --config .rtlflow/adopted/<name>/block.yaml --flow lint_only
```

## Add A Check

Add a check class in `rtlflow/checks.py`, register it in `CHECKS`, and add its
default config to `rtlflow.yaml`. The check should return `Finding` objects so
waivers, gates, and reports keep working unchanged.

## Add A Stage

Implement the `Stage` protocol: `name`, `available()`, and
`run(cfg, ctx, dry_run=False) -> StageResult`. Register the stage in `STAGES`
and add it to one or more flows in `rtlflow.yaml`.

## Daily Commands

```bash
rtlflow run --all --flow quick --jobs 4
rtlflow run --all --flow quick --jobs 1 --no-cache
rtlflow baseline save --all
rtlflow run --all --compare-to baseline
rtlflow cache clear
```
