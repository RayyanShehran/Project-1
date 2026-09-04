# Interpret Results

Use this when reading `results.json`, HTML reports, JUnit XML, cache output, or
baseline comparisons.

Commands:

```bash
rtlflow run --block fifo --flow full --report html,junit
rtlflow report work/fifo/<run_id>/results.json --format html,junit
rtlflow run --block fifo --flow quick --output json
rtlflow baseline save --all
rtlflow run --all --compare-to baseline
```

Statuses:

- `PASS`: stage or run completed without unwaived findings or gate failures.
- `FAIL`: stage ran and found RTL, lint, check, or gate failures.
- `ERROR`: infrastructure/tool problem such as timeout or crash.
- `SKIPPED`: stage did not run, usually because a tool is missing or gated.
- `CACHED`: result was reused from `work/cache/`.

Important fields:

- `schema_version`: result schema version.
- `manifest.git_sha` and `manifest.git_dirty`: reproducibility context.
- `manifest.tools`: real tool versions captured from installed executables.
- `summary`: counts by severity.
- `gate_failures`: quality gates that failed even if stages passed.

Comparison output:

- `NEW`: current finding was not in the saved baseline.
- `FIXED`: baseline finding is gone.
- `UNCHANGED`: finding exists in both runs.
