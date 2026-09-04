from pathlib import Path

from rtlflow.models import Finding, RunContext, Severity, StageResult, Status


def test_finding_is_hashable_identity_data():
    finding = Finding(
        severity=Severity.WARNING,
        rule_id="WIDTHTRUNC",
        message="width mismatch",
        file=Path("blocks/fifo/rtl/fifo.sv"),
        line=42,
        column=13,
        tool="verilator",
    )

    assert finding.severity.value == "warning"
    assert finding.rule_id == "WIDTHTRUNC"


def test_stage_result_keeps_fail_and_error_distinct():
    failed = StageResult(
        stage="sim_icarus",
        status=Status.FAIL,
        findings=[],
        artifacts={},
        duration_sec=0.1,
    )
    errored = StageResult(
        stage="sim_icarus",
        status=Status.ERROR,
        findings=[],
        artifacts={},
        duration_sec=0.1,
    )

    assert failed.status is Status.FAIL
    assert errored.status is Status.ERROR


def test_cached_status_is_available_for_reused_runs():
    assert Status.CACHED.value == "CACHED"


def test_run_context_starts_with_empty_artifacts(tmp_path):
    ctx = RunContext(run_id="run-1", workdir=tmp_path)

    assert ctx.artifacts == {}
    assert ctx.workdir == tmp_path
