import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

ROOT = Path(__file__).resolve().parents[1]
WORK_DIR = ROOT / "work" / "adder"
VVP_FILE = WORK_DIR / "sim.vvp"
VERILATOR_OBJ_DIR = Path("/tmp/rtlflow_adder_obj")


# Shared shape every simulator must follow.
class Simulator(Protocol):
    name: str

    def available(self) -> bool:
        ...

    def build(self, dry_run=False) -> None:
        ...

    def run(self, dry_run=False) -> None:
        ...


# Run one command and stop the script if it fails.
def run_cmd(cmd, dry_run=False):
    print("+", " ".join(str(x) for x in cmd))

    if dry_run:
        return

    result = subprocess.run(cmd, cwd=ROOT)

    if result.returncode != 0:
        raise SystemExit(result.returncode)


# Icarus flow: compile with iverilog, then run with vvp.
class IcarusSimulator:
    name = "icarus"

    def available(self):
        return shutil.which("iverilog") is not None and shutil.which("vvp") is not None

    def build(self, dry_run=False):
        run_cmd([
            "iverilog",
            "-g2012",
            "-o",
            str(VVP_FILE),
            "-f",
            "blocks/adder/files.f",
        ], dry_run)

    def run(self, dry_run=False):
        run_cmd([
            "vvp",
            str(VVP_FILE),
        ], dry_run)


# Verilator flow: build a native executable, then run it.
class VerilatorSimulator:
    name = "verilator"

    def available(self):
        return shutil.which("verilator") is not None

    def build(self, dry_run=False):
        run_cmd([
            "verilator",
            "--binary",
            "--timing",
            "--trace",
            "-Mdir",
            str(VERILATOR_OBJ_DIR),
            "-f",
            "blocks/adder/files.f",
            "--top-module",
            "adder_tb",
        ], dry_run)

    def run(self, dry_run=False):
        run_cmd([
            str(VERILATOR_OBJ_DIR / "Vadder_tb"),
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
    #   sim --sim icarus/verilator
    subparsers = parser.add_subparsers(dest="command", required=True)

    sim_parser = subparsers.add_parser("sim")
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
        WORK_DIR.mkdir(parents=True, exist_ok=True)

        sim = SIMULATORS[args.sim]

        if not sim.available():
            print(f"ERROR: simulator not available: {sim.name}")
            raise SystemExit(1)

        sim.build(args.dry_run)
        sim.run(args.dry_run)

        if args.dry_run:
            print("Dry run only; no files written")
        else:
            print(f"Wrote {WORK_DIR / 'waveform.vcd'}")


if __name__ == "__main__":
    main()