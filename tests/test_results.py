import json
import xml.etree.ElementTree as ET
from pathlib import Path

from rtlflow.models import Finding, Severity, StageResult, Status
from rtlflow.results import (
    build_results_document,
    generate_html_report,
    generate_junit_xml,
    load_results_json,
    write_results_json,
)


def make_stage(status=Status.PASS, findings=None):
    return StageResult(
        stage="lint_verilator",
        status=status,
        findings=findings or [],
        artifacts={"log": Path("work/adder/run/lint.log")},
        duration_sec=0.2,
    )


def make_finding(severity=Severity.WARNING):
    return Finding(
        severity=severity,
        rule_id="line-length",
        message="line too long",
        file=Path("blocks/adder/rtl/adder.sv"),
        line=12,
        column=3,
        tool="verible",
    )


def test_results_json_round_trip(tmp_path):
    data = build_results_document(
        {
            "run_id": "run-1",
            "block": "adder",
            "flow": "quick",
            "status": Status.PASS,
            "results": [make_stage()],
        },
        manifest={"git_sha": "abc", "git_dirty": False},
        gates={"max_errors": 0},
    )

    path = write_results_json(data, tmp_path)

    assert load_results_json(path) == data
    assert json.loads(path.read_text())["schema_version"] == 1


def test_quality_gate_can_fail_passing_stages():
    data = build_results_document(
        {
            "run_id": "run-1",
            "block": "adder",
            "flow": "quick",
            "status": Status.PASS,
            "results": [make_stage(findings=[make_finding()])],
        },
        manifest={},
        gates={"max_warnings": 0},
    )

    assert data["status"] == "FAIL"
    assert data["gate_failures"] == ["warnings 1 > max_warnings 0"]


def test_html_report_is_self_contained():
    data = build_results_document(
        {
            "run_id": "run-1",
            "block": "adder",
            "flow": "quick",
            "status": Status.FAIL,
            "results": [make_stage(Status.FAIL, [make_finding()])],
        },
        manifest={"tool": "version"},
        gates={},
    )

    html = generate_html_report(data)

    assert "<html" in html
    assert "line-length" in html
    assert "http://" not in html
    assert "https://" not in html


def test_junit_xml_is_parseable():
    data = build_results_document(
        {
            "run_id": "run-1",
            "block": "adder",
            "flow": "quick",
            "status": Status.FAIL,
            "results": [make_stage(Status.FAIL, [make_finding()])],
        },
        manifest={},
        gates={},
    )

    root = ET.fromstring(generate_junit_xml(data))

    assert root.tag == "testsuite"
    assert root.attrib["failures"] == "1"
