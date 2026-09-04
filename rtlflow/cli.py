import argparse
import contextlib
import io
import os
import shutil
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import yaml

from rtlflow.cache import (
    clear_cache,
    compute_input_hash,
    load_cached_results,
    materialize_cached_results,
    save_cached_results,
)
from rtlflow.baseline import compare_to_baseline, load_baseline, save_baseline
from rtlflow.checks import CHECKS, ChecksStage
from rtlflow.lint import VeribleLintStage, VerilatorLintStage
from rtlflow.models import Finding, RunContext, Severity, StageResult, Status
from rtlflow.results import (
    build_results_document,
    capture_manifest,
    load_results_json,
    write_report,
    write_results_json,
)
from rtlflow.waivers import apply_waivers, load_waivers

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FLOW_POLICY = "gated"

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
        "checks": load_project_config().get("checks", {}),
    }


def load_project_config():
    config_path = ROOT / "rtlflow.yaml"
    if not config_path.exists():
        return {"flows": {}}
    with config_path.open() as f:
        return yaml.safe_load(f) or {"flows": {}}


def block_config_path(block):
    return ROOT / "blocks" / block / "block.yaml"


def discover_blocks(root=ROOT):
    blocks_dir = root / "blocks"
    if not blocks_dir.exists():
        return []
    return sorted(
        path.name
        for path in blocks_dir.iterdir()
        if path.is_dir() and (path / "block.yaml").exists()
    )


def parse_block_list(blocks_text):
    return [
        item.strip()
        for item in (blocks_text or "").split(",")
        if item.strip()
    ]


def select_run_blocks(args, root=ROOT):
    if args.all and args.blocks:
        print("ERROR: use either --all or --blocks, not both")
        raise SystemExit(2)
    if args.all:
        blocks = discover_blocks(root)
        if not blocks:
            print("ERROR: no blocks found")
            raise SystemExit(1)
        return blocks
    if args.blocks:
        return parse_block_list(args.blocks)
    return [args.block]


def normalize_flow(flow_config):
    if isinstance(flow_config, list):
        return {"policy": DEFAULT_FLOW_POLICY, "stages": flow_config}
    return {
        "policy": flow_config.get("policy", DEFAULT_FLOW_POLICY),
        "stages": flow_config.get("stages", []),
    }


def make_run_id():
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{uuid4().hex[:6]}"


def format_stage_line(result):
    return (
        f"{result.stage:<16} {result.status.value:<7} "
        f"{result.duration_sec:>5.1f}s {len(result.findings):>3} findings"
    )


def skipped_stage_result(stage_name, cfg, reason):
    return StageResult(
        stage=stage_name,
        status=Status.SKIPPED,
        findings=[
            Finding(
                severity=Severity.INFO,
                rule_id="SKIPPED",
                message=reason,
                file=Path(cfg["sources"]),
                line=None,
                column=None,
                tool=stage_name,
            )
        ],
        artifacts={},
        duration_sec=0.0,
    )


def should_gate_simulation(results):
    for result in results:
        if result.stage.startswith("sim_"):
            continue
        if any(finding.severity is Severity.ERROR for finding in result.findings):
            return True
    return False


def run_flow(
    block,
    flow,
    *,
    only=None,
    skip=None,
    continue_on_error=False,
    dry_run=False,
    stage_registry=None,
    project_config=None,
):
    cfg = load_block_config(block)
    project_config = project_config or load_project_config()
    flows = project_config.get("flows", {})
    if flow not in flows:
        print(f"ERROR: unknown flow: {flow}")
        raise SystemExit(1)

    flow_config = normalize_flow(flows[flow])
    policy = "run_all" if continue_on_error else flow_config["policy"]
    stage_names = list(flow_config["stages"])
    if only:
        selected = set(only)
        stage_names = [name for name in stage_names if name in selected]
    if skip:
        skipped = set(skip)
        stage_names = [name for name in stage_names if name not in skipped]

    registry = stage_registry or STAGES
    run_id = make_run_id()
    run_workdir = cfg["base_work_dir"] / run_id
    results = []

    for stage_name in stage_names:
        if stage_name not in registry:
            result = skipped_stage_result(stage_name, cfg, "stage is not registered")
            results.append(result)
            print(format_stage_line(result))
            continue

        if (
            policy == "gated"
            and stage_name.startswith("sim_")
            and should_gate_simulation(results)
        ):
            result = skipped_stage_result(stage_name, cfg, "skipped by gated flow policy")
            results.append(result)
            print(format_stage_line(result))
            continue

        stage = registry[stage_name]
        ctx = RunContext(run_id=run_id, workdir=run_workdir / stage_name)
        if stage_name.startswith("lint_") or stage_name == "checks":
            result = stage.run(cfg, ctx, dry_run, ROOT)
            remaining_findings, audit = apply_waivers(result.findings, cfg["waivers"])
            result.findings = remaining_findings
            if audit.expired:
                result.status = Status.FAIL
            elif result.status is Status.FAIL and not result.findings:
                result.status = Status.PASS
        else:
            result = stage.run(cfg, ctx, dry_run)

        results.append(result)
        print(format_stage_line(result))

        if policy == "fail_fast" and result.status in {Status.FAIL, Status.ERROR}:
            break

    failed = [result for result in results if result.status in {Status.FAIL, Status.ERROR}]
    overall = Status.FAIL if failed else Status.PASS
    return {
        "block": block,
        "flow": flow,
        "run_id": run_id,
        "workdir": run_workdir,
        "status": overall,
        "results": results,
    }


def run_block_with_results(
    block,
    flow,
    *,
    only=None,
    skip=None,
    continue_on_error=False,
    dry_run=False,
    report="",
    no_cache=False,
):
    cfg = load_block_config(block)
    project_config = load_project_config()
    manifest = capture_manifest(
        ROOT,
        [ROOT / "rtlflow.yaml", block_config_path(block)],
    )
    input_hash = compute_input_hash(
        ROOT,
        cfg,
        flow,
        project_config,
        manifest.get("tools", {}),
    )
    if not no_cache:
        cached = load_cached_results(ROOT, input_hash)
        if cached is not None:
            cache_source_run_id = cached.get("run_id")
            cached["cache_source_run_id"] = cache_source_run_id
            cached["run_id"] = make_run_id()
            cached["input_hash"] = input_hash
            workdir = cfg["base_work_dir"] / cached["run_id"]
            results_path = materialize_cached_results(cached, workdir)
            print(f"CACHED {block} from {cache_source_run_id}")
            print(f"Wrote {results_path}")
            for report_format in [item.strip() for item in report.split(",") if item.strip()]:
                report_path = write_report(cached, workdir, report_format)
                print(f"Wrote {report_path}")
            return cached

    flow_result = run_flow(
        block,
        flow,
        only=only,
        skip=skip,
        continue_on_error=continue_on_error,
        dry_run=dry_run,
    )
    results_doc = build_results_document(
        flow_result,
        manifest,
        project_config.get("gates", {}),
    )
    results_doc["input_hash"] = input_hash
    results_doc["cached"] = False
    results_path = write_results_json(results_doc, flow_result["workdir"])
    save_cached_results(ROOT, input_hash, results_doc)
    print(f"Wrote {results_path}")
    for report_format in [item.strip() for item in report.split(",") if item.strip()]:
        report_path = write_report(results_doc, flow_result["workdir"], report_format)
        print(f"Wrote {report_path}")
    for failure in results_doc["gate_failures"]:
        print(f"gate failure: {failure}")

    total_findings = sum(len(stage.findings) for stage in flow_result["results"])
    print(
        f"{results_doc['status']} - {total_findings} findings "
        f"across {len(flow_result['results'])} stages"
    )
    return results_doc


def run_block_worker(kwargs):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        results_doc = run_block_with_results(**kwargs)
    return results_doc, output.getvalue()


def run_blocks(
    blocks,
    flow,
    *,
    only=None,
    skip=None,
    continue_on_error=False,
    dry_run=False,
    report="",
    fail_fast=False,
    jobs=None,
    no_cache=False,
    runner=run_block_with_results,
):
    jobs = jobs or os.cpu_count() or 1
    results_docs = []
    run_kwargs = [
        {
            "block": block,
            "flow": flow,
            "only": only,
            "skip": skip,
            "continue_on_error": continue_on_error,
            "dry_run": dry_run,
            "report": report,
            "no_cache": no_cache,
        }
        for block in blocks
    ]

    if jobs == 1 or len(blocks) <= 1 or runner is not run_block_with_results:
        for kwargs in run_kwargs:
            if len(blocks) > 1:
                print(f"== {kwargs['block']} ==")
            results_doc = runner(**kwargs)
            results_docs.append(results_doc)
            if fail_fast and results_doc["status"] != Status.PASS.value:
                break
        return results_docs

    with ProcessPoolExecutor(max_workers=jobs) as executor:
        futures = {
            executor.submit(run_block_worker, kwargs): kwargs["block"]
            for kwargs in run_kwargs
        }
        for future in as_completed(futures):
            block = futures[future]
            print(f"== {block} ==")
            results_doc, output = future.result()
            print(output, end="")
            results_docs.append(results_doc)
            if fail_fast and results_doc["status"] != Status.PASS.value:
                for pending in futures:
                    pending.cancel()
                break

    return results_docs


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
    for stage in [*SIMULATORS.values(), *LINTERS.values(), ChecksStage()]
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

    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--block", default="adder")
    check_parser.add_argument("--dry-run", action="store_true")

    subparsers.add_parser("list-checks")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--block", default="adder")
    run_parser.add_argument("--all", action="store_true")
    run_parser.add_argument("--blocks")
    run_parser.add_argument("--flow", default="quick")
    run_parser.add_argument("--only", action="append", default=[])
    run_parser.add_argument("--skip", action="append", default=[])
    run_parser.add_argument("--continue-on-error", action="store_true")
    run_parser.add_argument("--fail-fast", action="store_true")
    run_parser.add_argument("--jobs", type=int)
    run_parser.add_argument("--no-cache", action="store_true")
    run_parser.add_argument("--compare-to")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--report", default="")

    subparsers.add_parser("list-flows")

    baseline_parser = subparsers.add_parser("baseline")
    baseline_parser.add_argument("action", choices=["save"])
    baseline_parser.add_argument("--all", action="store_true")
    baseline_parser.add_argument("--blocks")
    baseline_parser.add_argument("--block", default="adder")

    cache_parser = subparsers.add_parser("cache")
    cache_parser.add_argument("action", choices=["clear"])

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("results_json")
    report_parser.add_argument("--format", default="html")

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

    if args.command == "list-flows":
        for name, flow_config in load_project_config().get("flows", {}).items():
            flow_config = normalize_flow(flow_config)
            stages = ", ".join(flow_config["stages"])
            print(f"{name}: {stages} ({flow_config['policy']})")
        return

    if args.command == "list-checks":
        config = load_project_config().get("checks", {})
        for rule_id, check in CHECKS.items():
            rule_config = config.get(rule_id, {})
            status = "enabled" if rule_config.get("enabled", True) else "disabled"
            severity = rule_config.get("severity", check.default_severity.value)
            print(f"{rule_id}: {status}, {severity} - {check.description}")
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

    if args.command == "check":
        cfg = load_block_config(args.block)
        stage = STAGES["checks"]
        ctx = RunContext(run_id=stage.name, workdir=cfg["base_work_dir"] / stage.name)
        result = stage.run(cfg, ctx, args.dry_run, ROOT)
        remaining_findings, audit = apply_waivers(result.findings, cfg["waivers"])
        result.findings = remaining_findings
        if audit.expired:
            result.status = Status.FAIL
        elif result.status is Status.FAIL and not result.findings:
            result.status = Status.PASS
        for finding in result.findings:
            print(
                f"{finding.severity.value}: {finding.file}:{finding.line}:{finding.column}: "
                f"{finding.message} [{finding.rule_id}]"
            )
        print(format_stage_line(result))
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

    if args.command == "run":
        blocks = select_run_blocks(args)
        results_docs = run_blocks(
            blocks,
            args.flow,
            only=args.only,
            skip=args.skip,
            continue_on_error=args.continue_on_error,
            dry_run=args.dry_run,
            report=args.report,
            fail_fast=args.fail_fast,
            jobs=args.jobs,
            no_cache=args.no_cache,
        )

        failed = [doc for doc in results_docs if doc["status"] != Status.PASS.value]
        if args.compare_to:
            try:
                baseline = load_baseline(ROOT, args.compare_to)
            except (FileNotFoundError, ValueError) as e:
                print(f"ERROR: {e}")
                raise SystemExit(1) from e
            for doc in results_docs:
                comparison = compare_to_baseline(doc, baseline)
                doc["comparison"] = comparison
                print(
                    f"{doc['block']} comparison: "
                    f"{len(comparison['new'])} NEW, "
                    f"{len(comparison['fixed'])} FIXED, "
                    f"{len(comparison['unchanged'])} UNCHANGED"
                )
                for item in comparison["new"]:
                    print(f"NEW {item}")
        print(
            f"{len(results_docs)} blocks - "
            f"{len(results_docs) - len(failed)} passed, {len(failed)} failed"
        )
        if failed:
            raise SystemExit(1)

    if args.command == "baseline":
        blocks = select_run_blocks(args)
        path = save_baseline(ROOT, blocks)
        print(f"Wrote {path}")

    if args.command == "cache":
        if args.action == "clear":
            cleared = clear_cache(ROOT)
            print("cache cleared" if cleared else "cache already empty")

    if args.command == "report":
        data = load_results_json(Path(args.results_json))
        workdir = Path(args.results_json).resolve().parent
        for report_format in [item.strip() for item in args.format.split(",") if item.strip()]:
            report_path = write_report(data, workdir, report_format)
            print(f"Wrote {report_path}")


IcarusSimulator = IcarusSimulationStage
VerilatorSimulator = VerilatorSimulationStage


if __name__ == "__main__":
    main()
