import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

import yaml

ROOT = Path(__file__).resolve().parents[1]


# Shared shape every simulator must follow.
class Simulator(Protocol):
    name: str

    def available(self) -> bool:
        ...

    def build(self, cfg, dry_run=False) -> None:
        ...

    def run(self, cfg, dry_run=False) -> None:
        ...


# Run one command and stop the script if it fails.
def run_cmd(cmd, dry_run=False):
    print("+", " ".join(str(x) for x in cmd))

    if dry_run:
        return

    result = subprocess.run(cmd, cwd=ROOT)

    if result.returncode != 0:
        raise SystemExit(result.returncode)


# Read block settings from blocks/<block>/block.yaml.
def load_block_config(block_name):
    config_path = ROOT / "blocks" / block_name / "block.yaml"

    if not config_path.exists():
        print(f"ERROR: missing config file: {config_path}")
        raise SystemExit(1)

    with config_path.open() as f:
        cfg = yaml.safe_load(f)

    required_fields = ["name", "top", "sources", "timeout_sec"]

    for field in required_fields:
        if field not in cfg:
            print(f"ERROR: {config_path} missing required field: {field}")
            raise SystemExit(1)

    block_dir = ROOT / "blocks" / cfg["name"]
    sources = block_dir / cfg["sources"]

    if not sources.exists():
        print(f"ERROR: source file list does not exist: {sources}")
        raise SystemExit(1)

    work_dir = ROOT / "work" / cfg["name"]

    return {
        "name": cfg["name"],
        "top": cfg["top"],
        "sources": str(sources),
        "timeout_sec": cfg["timeout_sec"],
        "work_dir": work_dir,
        "vvp_file": work_dir / "sim.vvp",
        "waveform": work_dir / "waveform.vcd",
        "verilator_obj_dir": Path(f"/tmp/rtlflow_{cfg['name']}_obj"),
    }


# Icarus flow: compile with iverilog, then run with vvp.
class IcarusSimulator:
    name = "icarus"

    def available(self):
        return shutil.which("iverilog") is not None and shutil.which("vvp") is not None

    def build(self, cfg, dry_run=False):
        run_cmd([
            "iverilog",
            "-g2012",
            "-o",
            str(cfg["vvp_file"]),
            "-f",
            cfg["sources"],
        ], dry_run)

    def run(self, cfg, dry_run=False):
        run_cmd([
            "vvp",
            str(cfg["vvp_file"]),
        ], dry_run)


# Verilator flow: build a native executable, then run it.
class VerilatorSimulator:
    name = "verilator"

    def available(self):
        return shutil.which("verilator") is not None

    def build(self, cfg, dry_run=False):
        run_cmd([
            "verilator",
            "--binary",
            "--timing",
            "--trace",
            "-Mdir",
            str(cfg["verilator_obj_dir"]),
            "-f",
            cfg["sources"],
            "--top-module",
            cfg["top"],
        ], dry_run)

    def run(self, cfg, dry_run=False):
        run_cmd([
            str(cfg["verilator_obj_dir"] / f"V{cfg['top']}"),
        ], dry_run)


# Simple registry for the simulators this tool supports.
SIMULATORS = {
    "icarus": IcarusSimulator(),
    "verilator": VerilatorSimulator(),
}


def main():
    parser = argparse.ArgumentParser()

    # Commands:
    #   list-sims
    #   sim --block adder --sim icarus/verilator
    subparsers = parser.add_subparsers(dest="command", required=True)

    sim_parser = subparsers.add_parser("sim")
    sim_parser.add_argument("--block", default="adder")
    sim_parser.add_argument("--sim", choices=SIMULATORS.keys(), default="icarus")
    sim_parser.add_argument("--dry-run", action="store_true")

    subparsers.add_parser("list-sims")

    args = parser.parse_args()

    if args.command == "list-sims":
        for name, sim in SIMULATORS.items():
            status = "available" if sim.available() else "missing"
            print(f"{name}: {status}")
        return

    if args.command == "sim":
        cfg = load_block_config(args.block)
        cfg["work_dir"].mkdir(parents=True, exist_ok=True)

        sim = SIMULATORS[args.sim]

        if not sim.available():
            print(f"ERROR: simulator not available: {sim.name}")
            raise SystemExit(1)

        sim.build(cfg, args.dry_run)
        sim.run(cfg, args.dry_run)

        if args.dry_run:
            print("Dry run only; no files written")
        else:
            print(f"Wrote {cfg['waveform']}")


if __name__ == "__main__":
    main()