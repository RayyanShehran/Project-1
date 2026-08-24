import subprocess
from pathlib import Path

# Project root folder: Idk-project-1
ROOT = Path(__file__).resolve().parents[1]

# Put generated waveform files under work/adder
WORK_DIR = ROOT / "work" / "adder"

# Verilator uses make, and make breaks if the path has spaces.
# So we put Verilator's build files in /tmp instead.
OBJ_DIR = Path("/tmp/rtlflow_adder_obj")

def run(cmd):
    # Print the command before running it
    print("+", " ".join(str(x) for x in cmd))

    result = subprocess.run(cmd, cwd=ROOT)

    # Stop if the command failed
    if result.returncode != 0:
        raise SystemExit(result.returncode)

def main():
    # Create work/adder if it does not already exist
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    # Compile the SystemVerilog testbench with Verilator
    run([
        "verilator",
        "--binary",
        "--timing",
        "--trace",
        "-Mdir",
        str(OBJ_DIR),
        "-f",
        "blocks/adder/files.f",
        "--top-module",
        "adder_tb",
    ])

    # Run the executable that Verilator built
    run([
        str(OBJ_DIR / "Vadder_tb"),
    ])

    print(f"Wrote {WORK_DIR / 'waveform.vcd'}")

if __name__ == "__main__":
    main()