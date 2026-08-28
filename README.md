# RTL Flow

Small SystemVerilog simulation flow for bringing up RTL blocks.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

## List Simulators

```bash
rtlflow list-sims
```

## Run Simulations

```bash
rtlflow sim --block adder --sim icarus
rtlflow sim --block adder --sim verilator
rtlflow sim --block fifo --sim icarus
rtlflow sim --block fifo --sim verilator
```

## Dry Run

```bash
rtlflow sim --block fifo --sim verilator --dry-run
```

## Tests

```bash
pytest -m "not integration"
pytest -m integration
```

Outputs are written under `work/<block>/<sim>/`.