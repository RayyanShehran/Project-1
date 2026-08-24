import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK_DIR = ROOT / "work" / "adder"
VVP_FILE = WORK_DIR / "sim.vvp"

def run(cmd):
    print("+", " ".join(str(x) for x in cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

def main():
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    run([
        "iverilog",
        "-g2012",
        "-o",
        str(VVP_FILE),
        "-f",
        "blocks/adder/files.f",
    ])

    run([
        "vvp",
        str(VVP_FILE),
    ])

    print(f"Wrote {WORK_DIR / 'waveform.vcd'}")

if __name__ == "__main__":
    main()