# Run Lint

Use this when you need semantic or style lint findings for one block.

Commands:

```bash
rtlflow lint --block fifo --tool verilator
rtlflow lint --block fifo --tool verible
rtlflow run --block fifo --flow lint_only
```

Outputs:

- Findings print as `severity: file:line:column: message [rule]`.
- `TOOL_MISSING` means the executable is not installed.
- Waived findings are suppressed; expired and stale waivers are reported.
- `results.json` is written for flow runs.

Common failures:

- Missing Verilator or Verible reports a skipped or missing-tool stage.
- Expired waivers fail the command.
- Non-waived lint findings make the lint stage fail.
