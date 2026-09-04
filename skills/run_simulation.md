# Run Simulation

Use this when a block has a configured testbench and you need simulator results.

Commands:

```bash
rtlflow sim --block adder --sim icarus
rtlflow sim --block adder --sim verilator
rtlflow run --block adder --flow quick
rtlflow run --block adder --flow full
```

Outputs:

- Simulator logs and waveforms are written under `work/<block>/<run_id>/`.
- A simulation stage returns `PASS`, `FAIL`, `ERROR`, or `SKIPPED`.
- `FAIL` means the RTL/test failed after the tool ran.
- `ERROR` means the tool crashed, timed out, or could not run correctly.

Common failures:

- Missing simulator executable reports a skipped stage.
- A compile failure is a `FAIL` finding with rule `CompileError`.
- A timeout is an `ERROR` finding with rule `Timeout`.
