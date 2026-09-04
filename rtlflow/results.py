from __future__ import annotations

import hashlib
import html
import json
import os
import platform
import shutil
import socket
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from rtlflow.models import Finding, Severity, StageResult, Status


SCHEMA_VERSION = 1
KNOWN_TOOLS = {
    "verilator": ["verilator", "--version"],
    "iverilog": ["iverilog", "-V"],
    "vvp": ["vvp", "-V"],
    "verible": ["verible-verilog-lint", "--version"],
}


def capture_command_line(cmd: list[str], cwd: Path) -> str | None:
    if shutil.which(cmd[0]) is None:
        return None
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            timeout=5,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0] if output else None


def git_manifest(root: Path) -> dict:
    sha = capture_command_line(["git", "rev-parse", "HEAD"], root)
    dirty = None
    if shutil.which("git") is not None:
        try:
            dirty_result = subprocess.run(
                ["git", "status", "--short"],
                cwd=root,
                timeout=5,
                text=True,
                capture_output=True,
            )
            dirty = bool(dirty_result.stdout.strip())
        except (OSError, subprocess.TimeoutExpired):
            dirty = None
    return {"git_sha": sha, "git_dirty": dirty}


def hash_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda value: value.as_posix()):
        if not path.exists():
            continue
        digest.update(path.as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def capture_manifest(root: Path, config_paths: list[Path]) -> dict:
    manifest = git_manifest(root)
    manifest.update(
        {
            "config_hash": hash_files(config_paths),
            "tools": {
                name: capture_command_line(cmd, root)
                for name, cmd in KNOWN_TOOLS.items()
            },
            "host": socket.gethostname(),
            "user": os.environ.get("USERNAME") or os.environ.get("USER"),
            "platform": platform.platform(),
        }
    )
    return manifest


def finding_to_dict(finding: Finding) -> dict:
    return {
        "severity": finding.severity.value,
        "rule_id": finding.rule_id,
        "message": finding.message,
        "file": finding.file.as_posix(),
        "line": finding.line,
        "column": finding.column,
        "tool": finding.tool,
    }


def stage_to_dict(stage: StageResult) -> dict:
    return {
        "stage": stage.stage,
        "status": stage.status.value,
        "findings": [finding_to_dict(finding) for finding in stage.findings],
        "artifacts": {
            name: path.as_posix()
            for name, path in stage.artifacts.items()
        },
        "duration_sec": stage.duration_sec,
    }


def summarize_findings(stage_results: list[StageResult]) -> dict:
    summary = {severity.value: 0 for severity in Severity}
    for stage in stage_results:
        for finding in stage.findings:
            summary[finding.severity.value] += 1
    return summary


def evaluate_gates(summary: dict, gates: dict) -> list[str]:
    failures = []
    max_errors = gates.get("max_errors")
    max_warnings = gates.get("max_warnings")
    if max_errors is not None and summary.get("error", 0) > max_errors:
        failures.append(f"errors {summary.get('error', 0)} > max_errors {max_errors}")
    if max_warnings is not None and summary.get("warning", 0) > max_warnings:
        failures.append(
            f"warnings {summary.get('warning', 0)} > max_warnings {max_warnings}"
        )
    return failures


def build_results_document(flow_result: dict, manifest: dict, gates: dict) -> dict:
    stage_results = flow_result["results"]
    summary = summarize_findings(stage_results)
    gate_failures = evaluate_gates(summary, gates)
    stage_failed = flow_result["status"] not in {Status.PASS, Status.CACHED}
    status = Status.FAIL.value if stage_failed or gate_failures else Status.PASS.value
    duration = sum(stage.duration_sec for stage in stage_results)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": flow_result["run_id"],
        "block": flow_result["block"],
        "flow": flow_result["flow"],
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_sec": duration,
        "status": status,
        "manifest": manifest,
        "stages": [stage_to_dict(stage) for stage in stage_results],
        "summary": summary,
        "gates": gates,
        "gate_failures": gate_failures,
    }


def write_results_json(data: dict, workdir: Path) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / "results.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return path


def load_results_json(path: Path) -> dict:
    return json.loads(path.read_text())


def generate_html_report(data: dict) -> str:
    rows = []
    for stage in data["stages"]:
        for finding in stage["findings"]:
            location = finding["file"]
            if finding["line"] is not None:
                location += f":{finding['line']}"
                if finding["column"] is not None:
                    location += f":{finding['column']}"
            rows.append(
                "<tr>"
                f"<td>{html.escape(stage['stage'])}</td>"
                f"<td>{html.escape(finding['severity'])}</td>"
                f"<td>{html.escape(finding['rule_id'])}</td>"
                f"<td>{html.escape(location)}</td>"
                f"<td>{html.escape(finding['message'])}</td>"
                "</tr>"
            )
    if not rows:
        rows.append("<tr><td colspan=\"5\">No findings</td></tr>")

    manifest = html.escape(json.dumps(data["manifest"], indent=2, sort_keys=True))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>rtlflow {html.escape(data['block'])} {html.escape(data['run_id'])}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #202124; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border: 1px solid #dadce0; padding: 8px; text-align: left; }}
    th {{ background: #f1f3f4; }}
    pre {{ background: #f8f9fa; padding: 12px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>rtlflow report: {html.escape(data['block'])}</h1>
  <p>Status: <strong>{html.escape(data['status'])}</strong></p>
  <p>Flow: {html.escape(data['flow'])} | Run: {html.escape(data['run_id'])}</p>
  <h2>Summary</h2>
  <pre>{html.escape(json.dumps(data['summary'], indent=2, sort_keys=True))}</pre>
  <h2>Findings</h2>
  <table>
    <thead><tr><th>Stage</th><th>Severity</th><th>Rule</th><th>Location</th><th>Message</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <h2>Manifest</h2>
  <pre>{manifest}</pre>
</body>
</html>
"""


def generate_junit_xml(data: dict) -> str:
    findings = [
        (stage, finding)
        for stage in data["stages"]
        for finding in stage["findings"]
    ]
    suite = ET.Element(
        "testsuite",
        {
            "name": f"rtlflow.{data['block']}.{data['flow']}",
            "tests": str(max(1, len(findings))),
            "failures": str(len(findings)),
            "errors": "0",
        },
    )
    if findings:
        for stage, finding in findings:
            case = ET.SubElement(
                suite,
                "testcase",
                {
                    "classname": stage["stage"],
                    "name": f"{finding['rule_id']}:{finding['file']}:{finding['line']}",
                },
            )
            failure = ET.SubElement(
                case,
                "failure",
                {
                    "type": finding["severity"],
                    "message": finding["message"],
                },
            )
            failure.text = json.dumps(finding, sort_keys=True)
    else:
        ET.SubElement(suite, "testcase", {"classname": "rtlflow", "name": "no_findings"})
    return ET.tostring(suite, encoding="unicode")


def write_report(data: dict, workdir: Path, report_format: str) -> Path:
    if report_format == "html":
        path = workdir / "report.html"
        path.write_text(generate_html_report(data))
        return path
    if report_format == "junit":
        path = workdir / "junit.xml"
        path.write_text(generate_junit_xml(data))
        return path
    raise ValueError(f"unknown report format: {report_format}")
