# RTL Flow

`rtlflow` runs a small SystemVerilog bring-up flow: lint, project checks,
simulation, structured results, reports, cache, baselines, and adoption of RTL
outside `blocks/`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

Optional external tools:

- `iverilog` and `vvp` for Icarus simulation
- `verilator` for Verilator simulation and lint
- `verible-verilog-lint` for Verible style lint

The unit tests pass without these tools installed; integration tests skip
missing tools.

## Simulators

```bash
rtlflow list-sims
rtlflow sim --block adder --sim icarus
rtlflow sim --block fifo --sim verilator
rtlflow sim --block fifo --sim icarus --dry-run
```

## Lint And Checks

```bash
rtlflow lint --block fifo --tool verilator
rtlflow lint --block fifo --tool verible
rtlflow check --block fifo
rtlflow list-checks
rtlflow waivers --block fifo --audit
```

Checks are configured in `rtlflow.yaml`. Current rules:

- `reset-port-naming`
- `no-bare-always`
- `module-filename-match`

Current limitation: custom checks use source scanning after stripping comments
and strings. They are tested for the starter rules, but they do not yet use
Verible JSON parse trees as the full project spec recommends.

## Flows

```bash
rtlflow list-flows
rtlflow run --block fifo --flow quick
rtlflow run --block fifo --flow full --jobs 1
rtlflow run --all --flow quick
rtlflow run --blocks adder,counter --flow lint_only
rtlflow run --block fifo --flow full --only checks
rtlflow run --block fifo --flow full --skip sim_verilator
rtlflow run --block fifo --flow full --continue-on-error
```

Each run writes `work/<block>/<run_id>/results.json`. Flow policies are defined
in `rtlflow.yaml`; the default project policy is gated, so simulation is skipped
after lint/check errors.

## Reports

```bash
rtlflow run --block fifo --flow full --report html,junit
rtlflow report work/fifo/<run_id>/results.json --format html,junit
```

Reports are regenerated from stored `results.json`, not live state.

## Cache And Baselines

```bash
rtlflow run --all --flow quick
rtlflow run --all --flow quick --no-cache
rtlflow cache clear
rtlflow baseline save --all
rtlflow run --all --compare-to baseline
```

The cache key includes source files, block config, flow/check config, selected
flow, and captured tool versions. Baseline comparison reports NEW, FIXED, and
UNCHANGED findings.

## Adopt External RTL

```bash
rtlflow adopt path/to/rtl
rtlflow adopt path/to/rtl --write-config .rtlflow/adopted/decoder/block.yaml
rtlflow adopt path/to/rtl --run --flow lint_only
rtlflow run --config .rtlflow/adopted/decoder/block.yaml --flow lint_only
```

Adoption infers source files, top candidates, testbench presence, and include
directories. Ambiguous top modules are reported instead of guessed.

## JSON Output

```bash
rtlflow run --block fifo --flow quick --output json
rtlflow run --all --flow quick --output json
```

JSON mode keeps machine-readable JSON on stdout and progress output on stderr.

## Tests

```bash
pytest -m "not integration"
pytest -m integration
```

Generated artifacts live under `work/`, which is ignored by git.
