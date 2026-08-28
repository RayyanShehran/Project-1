import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

import yaml

ROOT = Path(__file__).resolve().parents[1]

class RtlFlowError(Exception):
    pass


class ToolNotFound(RtlFlowError):
    pass


class CompileError(RtlFlowError):
    pass


class SimulationFailed(RtlFlowError):
    pass


class Timeout(RtlFlowError):
    pass


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
def run_cmd(cmd, cfg=None, dry_run=False, timeout_sec=None, phase="run"):
    command_text = "+ " + " ".join(str(x) for x in cmd)
    print(command_text)

    if cfg is not None:
        with cfg["log_file"].open("a") as f:
            f.write(command_text + "\n")

    if dry_run:
        return

    try:
        result = subprocess.run(
            cmd,
            cwd=ROOT,
            timeout=timeout_sec,
            text=True,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        message = f"ERROR: command timed out after {timeout_sec} seconds"
        print(message)

        if cfg is not None:
            with cfg["log_file"].open("a") as f:
                f.write(message + "\n")

        raise Timeout(message)

    if result.stdout:
        print(result.stdout, end="")
        if cfg is not None:
            with cfg["log_file"].open("a") as f:
                f.write(result.stdout)

    if result.stderr:
        print(result.stderr, end="")
        if cfg is not None:
            with cfg["log_file"].open("a") as f:
                f.write(result.stderr)

    if result.returncode != 0:
        if phase == "build":
            raise CompileError(f"build failed with exit code {result.returncode}")
        raise SimulationFailed(f"simulation failed with exit code {result.returncode}")

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
        "base_work_dir": work_dir,
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
        ], cfg, dry_run, cfg["timeout_sec"], phase="build")

    def run(self, cfg, dry_run=False):
        run_cmd([
            "vvp",
            str(cfg["vvp_file"]),
        ], cfg, dry_run, cfg["timeout_sec"], phase="run")


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
        ], cfg, dry_run, cfg["timeout_sec"], phase="build")

    def run(self, cfg, dry_run=False):
        run_cmd([
            str(cfg["verilator_obj_dir"] / f"V{cfg['top']}"),
        ], cfg, dry_run, cfg["timeout_sec"], phase="run")


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
        cfg["work_dir"] = cfg["base_work_dir"] / args.sim
        cfg["work_dir"].mkdir(parents=True, exist_ok=True)
        cfg["vvp_file"] = cfg["work_dir"] / "sim.vvp"
        cfg["waveform"] = cfg["work_dir"] / "waveform.vcd"
        
        cfg["log_file"] = cfg["work_dir"] / "run.log"
        sim = SIMULATORS[args.sim]

        if not sim.available():
            print(f"ERROR: simulator not available: {sim.name}")
            raise SystemExit(1)

        try:
            sim.build(cfg, args.dry_run)
            sim.run(cfg, args.dry_run)
        except RtlFlowError as e:
            print(f"ERROR [{type(e).__name__}]: {e}")
            raise SystemExit(1)

        if args.dry_run:
            print("Dry run only; no files written")
        else:
            print(f"Wrote {cfg['waveform']}")


if __name__ == "__main__":
    main()