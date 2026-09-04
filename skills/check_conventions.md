# Check Conventions

Use this when you need project-specific RTL checks rather than external lint.

Commands:

```bash
rtlflow check --block fifo
rtlflow list-checks
rtlflow run --block fifo --flow lint_only
```

Current rules:

- `reset-port-naming`: reset ports must match the configured pattern.
- `no-bare-always`: use `always_ff`, `always_comb`, or `always_latch`.
- `module-filename-match`: one module per file, matching the file stem.

Rule settings live in `rtlflow.yaml` under `checks`. Each rule can be disabled
or assigned a different severity there.

Common failures:

- Existing blocks may need either RTL fixes or justified waivers.
- `no-bare-always` ignores comments and string literals before scanning.
