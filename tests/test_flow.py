from pathlib import Path

from argparse import Namespace

import pytest

from rtlflow.cli import discover_blocks, parse_block_list, run_flow, select_run_blocks
from rtlflow.models import Finding, Severity, StageResult, Status


class FakeStage:
    def __init__(self, name, status=Status.PASS, findings=None):
        self.name = name
        self.status = status
        self.findings = findings or []

    def available(self):
        return True

    def run(self, cfg, ctx, dry_run=False, root=None):
        return StageResult(
            stage=self.name,
            status=self.status,
            findings=list(self.findings),
            artifacts={"log": ctx.workdir / "run.log"},
            duration_sec=0.01,
        )


def error_finding():
    return Finding(
        severity=Severity.ERROR,
        rule_id="WIDTH",
        message="width error",
        file=Path("blocks/adder/rtl/adder.sv"),
        line=3,
        column=1,
        tool="lint_verilator",
    )


def test_run_flow_run_all_collects_failures(capsys):
    result = run_flow(
        "adder",
        "full",
        continue_on_error=True,
        stage_registry={
            "lint_verilator": FakeStage("lint_verilator", Status.FAIL, [error_finding()]),
            "sim_icarus": FakeStage("sim_icarus"),
        },
        project_config={
            "flows": {
                "full": {
                    "policy": "fail_fast",
                    "stages": ["lint_verilator", "sim_icarus"],
                }
            }
        },
    )

    assert result["status"] is Status.FAIL
    assert [stage.stage for stage in result["results"]] == ["lint_verilator", "sim_icarus"]
    assert "sim_icarus" in capsys.readouterr().out


def test_run_flow_fail_fast_stops_after_failure():
    result = run_flow(
        "adder",
        "full",
        stage_registry={
            "lint_verilator": FakeStage("lint_verilator", Status.FAIL, [error_finding()]),
            "sim_icarus": FakeStage("sim_icarus"),
        },
        project_config={
            "flows": {
                "full": {
                    "policy": "fail_fast",
                    "stages": ["lint_verilator", "sim_icarus"],
                }
            }
        },
    )

    assert [stage.stage for stage in result["results"]] == ["lint_verilator"]


def test_run_flow_gated_skips_sim_after_lint_error():
    result = run_flow(
        "adder",
        "full",
        stage_registry={
            "lint_verilator": FakeStage("lint_verilator", Status.FAIL, [error_finding()]),
            "sim_icarus": FakeStage("sim_icarus"),
        },
        project_config={
            "flows": {
                "full": {
                    "policy": "gated",
                    "stages": ["lint_verilator", "sim_icarus"],
                }
            }
        },
    )

    assert [stage.status for stage in result["results"]] == [Status.FAIL, Status.SKIPPED]


def test_run_flow_only_and_skip_filter_stages():
    result = run_flow(
        "adder",
        "full",
        only=["lint_verilator", "sim_icarus"],
        skip=["sim_icarus"],
        stage_registry={
            "lint_verilator": FakeStage("lint_verilator"),
            "sim_icarus": FakeStage("sim_icarus"),
        },
        project_config={
            "flows": {
                "full": {
                    "policy": "run_all",
                    "stages": ["lint_verilator", "sim_icarus"],
                }
            }
        },
    )

    assert [stage.stage for stage in result["results"]] == ["lint_verilator"]


def test_discover_blocks_finds_configured_block_directories(tmp_path):
    (tmp_path / "blocks" / "adder").mkdir(parents=True)
    (tmp_path / "blocks" / "adder" / "block.yaml").write_text("name: adder\n")
    (tmp_path / "blocks" / "scratch").mkdir()

    assert discover_blocks(tmp_path) == ["adder"]


def test_parse_block_list_trims_comma_separated_names():
    assert parse_block_list("adder, fifo,, counter ") == ["adder", "fifo", "counter"]


def test_select_run_blocks_prefers_all_or_blocks(tmp_path):
    (tmp_path / "blocks" / "fifo").mkdir(parents=True)
    (tmp_path / "blocks" / "fifo" / "block.yaml").write_text("name: fifo\n")

    all_args = Namespace(all=True, blocks=None, block="adder")
    explicit_args = Namespace(all=False, blocks="adder,counter", block="fifo")

    assert select_run_blocks(all_args, tmp_path) == ["fifo"]
    assert select_run_blocks(explicit_args, tmp_path) == ["adder", "counter"]


def test_select_run_blocks_rejects_all_with_blocks():
    args = Namespace(all=True, blocks="adder", block="fifo")

    with pytest.raises(SystemExit):
        select_run_blocks(args)
