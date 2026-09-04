import argparse
import shutil
import subprocess
import time
from pathlib import Path
from typing import Protocol

import yaml

from rtlflow.lint import VeribleLintStage, VerilatorLintStage
from rtlflow.models import Finding, RunContext, Severity, StageResult, Status
from rtlflow.waivers import apply_waivers, load_waivers

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


# Shared shape every stage in the flow must follow.
class Stage(Protocol):
    name: str

    def available(self) -> bool:
        ...

    def run(self, cfg, ctx: RunContext, dry_run=False) -> StageResult:
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
    except FileNotFoundError as e:
        message = f"ERROR: tool not found: {cmd[0]}"
        print(message)

        if cfg is not None:
            with cfg["log_file"].open("a") as f:
                f.write(message + "\n")

        raise ToolNotFound(message) from e
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


def parameter_args_for_icarus(parameters):
    args = []

    for name, value in parameters.items():
        args.extend(["-P", f"{name}={value}"])

    return args


def parameter_args_for_verilator(parameters):
    args = []

    for name, value in parameters.items():
        args.append(f"-G{name}={value}")

    return args


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

    try:
        waivers = load_waivers(cfg.get("waivers", []), config_path)
    except ValueError as e:
        print(f"ERROR: {e}")
        raise SystemExit(1) from e

    return {
        "name": cfg["name"],
        "top": cfg["top"],
        "sources": str(sources),
        "parameters": cfg.get("parameters", {}),
        "timeout_sec": cfg["timeout_sec"],
        "base_work_dir": work_dir,
        "verilator_obj_dir": Path(f"/tmp/rtlflow_{cfg['name']}_obj"),
        "waivers": waivers,
    }


def finding_from_error(stage_name, cfg, error):
    return Finding(
        severity=Severity.ERROR,
        rule_id=type(error).__name__,
        message=str(error),
        file=Path(cfg["sources"]),
        line=None,
        column=None,
        tool=stage_name,
    )


class SimulationStage:
    simulator_name: str
    name: str

    def build(self, cfg, dry_run=False):
        raise NotImplementedError

    def execute(self, cfg, dry_run=False):
        raise NotImplementedError

    def prepare_config(self, cfg, ctx):
        cfg = dict(cfg)
        cfg["work_dir"] = ctx.workdir
        cfg["work_dir"].mkdir(parents=True, exist_ok=True)
        cfg["vvp_file"] = cfg["work_dir"] / "sim.vvp"
        cfg["waveform"] = cfg["work_dir"] / "waveform.vcd"
        cfg["log_file"] = cfg["work_dir"] / "run.log"
        return cfg

    def run(self, cfg, ctx: RunContext, dry_run=False) -> StageResult:
        started = time.perf_counter()
        cfg = self.prepare_config(cfg, ctx)
        artifacts = {"log": cfg["log_file"], "waveform": cfg["waveform"]}

        if not dry_run and not self.available():
            finding = Finding(
                severity=Severity.INFO,
                rule_id="TOOL_MISSING",
                message=f"simulator not available: {self.simulator_name}",
                file=Path(cfg["sources"]),
                line=None,
                column=None,
                tool=self.name,
            )
            return StageResult(
                stage=self.name,
                status=Status.SKIPPED,
                findings=[finding],
                artifacts=artifacts,
                duration_sec=time.perf_counter() - started,
            )

        try:
            self.build(cfg, dry_run)
            self.execute(cfg, dry_run)
        except (CompileError, SimulationFailed) as e:
            return StageResult(
                stage=self.name,
                status=Status.FAIL,
                findings=[finding_from_error(self.name, cfg, e)],
                artifacts=artifacts,
                duration_sec=time.perf_counter() - started,
            )
        except RtlFlowError as e:
            return StageResult(
                stage=self.name,
                status=Status.ERROR,
                findings=[finding_from_error(self.name, cfg, e)],
                artifacts=artifacts,
                duration_sec=time.perf_counter() - started,
            )

        return StageResult(
            stage=self.name,
            status=Status.PASS,
            findings=[],
            artifacts=artifacts,
            duration_sec=time.perf_counter() - started,
        )


# Icarus stage: compile with iverilog, then run with vvp.
class IcarusSimulationStage(SimulationStage):
    name = "sim_icarus"
    simulator_name = "icarus"

    def available(self):
        return shutil.which("iverilog") is not None and shutil.which("vvp") is not None

    def build(self, cfg, dry_run=False):
        cmd = [
            "iverilog",
            "-g2012",
            "-o",
            str(cfg["vvp_file"]),
            "-f",
            cfg["sources"],
        ]
        cmd.extend(parameter_args_for_icarus(cfg["parameters"]))
        run_cmd(cmd, cfg, dry_run, cfg["timeout_sec"], phase="build")

    def execute(self, cfg, dry_run=False):
        run_cmd([
            "vvp",
            str(cfg["vvp_file"]),
        ], cfg, dry_run, cfg["timeout_sec"], phase="run")


# Verilator stage: build a native executable, then run it.
class VerilatorSimulationStage(SimulationStage):
    name = "sim_verilator"
    simulator_name = "verilator"

    def available(self):
        return shutil.which("verilator") is not None

    def build(self, cfg, dry_run=False):
        cmd = [
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
        ]
        cmd.extend(parameter_args_for_verilator(cfg["parameters"]))

        run_cmd(cmd, cfg, dry_run, cfg["timeout_sec"], phase="build")

    def execute(self, cfg, dry_run=False):
        run_cmd([
            str(cfg["verilator_obj_dir"] / f"V{cfg['top']}"),
        ], cfg, dry_run, cfg["timeout_sec"], phase="run")


# Simple registry for the simulators this tool supports.
SIMULATORS = {
    "icarus": IcarusSimulationStage(),
    "verilator": VerilatorSimulationStage(),
}

LINTERS = {
    "verilator": VerilatorLintStage(),
    "verible": VeribleLintStage(),
}

STAGES = {
    stage.name: stage
    for stage in [*SIMULATORS.values(), *LINTERS.values()]
}


def classify_output(text):
    lowered = text.lower()

    if "unknown module type" in lowered or "elaboration" in lowered:
        return "ElaborationError"

    if "syntax error" in lowered or "invalid module item" in lowered:
        return "CompileError"

    if "fail" in lowered:
        return "SimulationFailed"

    if "pass" in lowered:
        return "Success"

    return "Unknown"


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

    lint_parser = subparsers.add_parser("lint")
    lint_parser.add_argument("--block", default="adder")
    lint_parser.add_argument("--tool", choices=LINTERS.keys(), default="verilator")
    lint_parser.add_argument("--dry-run", action="store_true")

    waivers_parser = subparsers.add_parser("waivers")
    waivers_parser.add_argument("--block", default="adder")
    waivers_parser.add_argument("--audit", action="store_true")

    subparsers.add_parser("list-sims")

    args = parser.parse_args()

    if args.command == "list-sims":
        for name, sim in SIMULATORS.items():
            status = "available" if sim.available() else "missing"
            print(f"{name}: {status}")
        return

    if args.command == "sim":
        cfg = load_block_config(args.block)
        sim = SIMULATORS[args.sim]
        ctx = RunContext(
            run_id=args.sim,
            workdir=cfg["base_work_dir"] / args.sim,
        )
        result = sim.run(cfg, ctx, args.dry_run)

        if result.status is not Status.PASS:
            for finding in result.findings:
                print(f"{result.status.value} [{finding.rule_id}]: {finding.message}")
            raise SystemExit(1)

        if args.dry_run:
            print("Dry run only; no files written")
        else:
            print(f"Wrote {result.artifacts['waveform']}")

    if args.command == "lint":
        cfg = load_block_config(args.block)
        lint_stage = LINTERS[args.tool]
        ctx = RunContext(
            run_id=lint_stage.name,
            workdir=cfg["base_work_dir"] / lint_stage.name,
        )
        result = lint_stage.run(cfg, ctx, args.dry_run, ROOT)
        remaining_findings, audit = apply_waivers(result.findings, cfg["waivers"])
        result.findings = remaining_findings
        if audit.expired:
            result.status = Status.FAIL
        elif result.status is Status.FAIL and not result.findings:
            result.status = Status.PASS

        for finding in result.findings:
            location = finding.file
            if finding.line is not None:
                location = f"{location}:{finding.line}"
                if finding.column is not None:
                    location = f"{location}:{finding.column}"
            print(
                f"{finding.severity.value}: {location}: "
                f"{finding.message} [{finding.rule_id}]"
            )

        for waiver in audit.expired:
            print(f"expired waiver: {waiver.file}:{waiver.line or '*'} [{waiver.rule}]")
        for waiver in audit.stale:
            print(f"stale waiver: {waiver.file}:{waiver.line or '*'} [{waiver.rule}]")
        if audit.waived_findings:
            print(f"waived {len(audit.waived_findings)} findings")

        print(
            f"{result.stage} {result.status.value} "
            f"{result.duration_sec:.1f}s {len(result.findings)} findings"
        )

        if result.status is not Status.PASS:
            raise SystemExit(1)

    if args.command == "waivers":
        if not args.audit:
            parser.error("waivers currently supports only --audit")
        cfg = load_block_config(args.block)
        _remaining, audit = apply_waivers([], cfg["waivers"])
        for waiver in audit.expired:
            print(f"expired waiver: {waiver.file}:{waiver.line or '*'} [{waiver.rule}]")
        for waiver in audit.stale:
            print(f"stale waiver: {waiver.file}:{waiver.line or '*'} [{waiver.rule}]")
        print(
            f"waivers: {len(cfg['waivers'])} total, "
            f"{len(audit.expired)} expired, {len(audit.stale)} stale"
        )
        if audit.expired or audit.stale:
            raise SystemExit(1)


IcarusSimulator = IcarusSimulationStage
VerilatorSimulator = VerilatorSimulationStage


if __name__ == "__main__":
    main()
