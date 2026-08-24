# RTL Flow

Small SystemVerilog simulation flow for bringing up RTL blocks.

## Run the adder simulation

From the project root, run:

```bash
python3 scripts/sim.py
```

## Phase 2 Notes

The first rough Verilator version duplicated most of `scripts/sim.py`.
Both scripts create work directories, run commands, check exit codes, and print output paths.
Only the compile/run commands are simulator-specific.
This is why the next step is to separate common flow logic from simulator-specific logic.