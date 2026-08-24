import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK_DIR = ROOT / "work" / "adder"
VVP_FILE = WORK_DIR / "sim.vvp"
VERILATOR_OBJ_DIR = Path("/tmp/rtlflow_adder_obj")

def run(cmd, dry_run=False):
    print("+", " ".join(str(x) for x in cmd))

    if dry_run:
        return

    result = subprocess.run(cmd, cwd=ROOT)

    if result.returncode != 0:
        raise SystemExit(result.returncode)

def run_icarus(dry_run=False):
    run([
        "iverilog",
        "-g2012",
        "-o",
        str(VVP_FILE),
        "-f",
        "blocks/adder/files.f",
    ], dry_run)

    run([
        "vvp",
        str(VVP_FILE),
    ], dry_run)

def run_verilator(dry_run=False):
    run([
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

    run([
        str(VERILATOR_OBJ_DIR / "Vadder_tb"),
    ], dry_run)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sim",
        choices=["icarus", "verilator"],
        default="icarus",
        help="Simulator to use",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without running them",
    )

    args = parser.parse_args()

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    if args.sim == "icarus":
        run_icarus(args.dry_run)
    elif args.sim == "verilator":
        run_verilator(args.dry_run)

    if args.dry_run:
        print("Dry run only; no files written")
    else:
        print(f"Wrote {WORK_DIR / 'waveform.vcd'}")

if __name__ == "__main__":
    main()