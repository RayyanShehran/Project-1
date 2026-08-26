# Phase 2 Notes

## What Phase 1 Got Wrong

Phase 1 proved the flow worked, but it hardcoded too much. The script assumed one block, one file list, one simulator, and one output directory. That was fine for proving the idea, but it would be painful to repeat for many blocks or tools.

The rough Verilator copy made the problem obvious. `sim.py` and `sim_verilator.py` duplicated command execution, work directory setup, error handling, and output reporting. Only the simulator commands were truly different.

## Why the Interface Looks This Way

The simulator interface uses three main operations:

- `available()` checks whether the simulator exists on the machine.
- `build()` compiles or builds the simulation.
- `run()` executes the compiled simulation.

This fits Icarus because it has a clear compile step and run step: `iverilog` then `vvp`.

It also fits Verilator because `build()` can cover Verilator's SystemVerilog-to-C++ build flow, and `run()` executes the generated binary. A simulator like Vivado XSim has more internal steps, but those can still live inside `build()` unless the tool needs finer-grained reporting later.

## What I Learned From Icarus vs Verilator

Icarus was more permissive and let some width issues pass. Verilator was stricter and caught width mismatches, such as comparing a small `count` signal against a wider integer parameter in the FIFO.

That difference is useful. Icarus helps show four-state simulation behavior, while Verilator acts like a strict lint/build tool. Running both gives better confidence than either one alone.