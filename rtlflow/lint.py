from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from rtlflow.models import Finding, RunContext, Severity, StageResult, Status


VERILATOR_RE = re.compile(r"^%(Warning|Error)(?:-([A-Za-z0-9_]+))?:\s+(.+)$")
VERIBLE_RE = re.compile(r"^(.+):(\d+):(\d+):\s+(.*?)\s+\[([^\]]+)\]\s*$")


def read_file_list(root: Path, sources: str) -> list[Path]:
    files = []
    sources_path = Path(sources)
    for line in sources_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path = Path(line)
        files.append(path if path.is_absolute() else root / path)
    return files


def parse_verilator_lint(text: str) -> list[Finding]:
    findings = []
    for line in text.splitlines():
        match = VERILATOR_RE.match(line.strip())
        if not match:
            continue

        severity_text, rule_id, location_text = match.groups()
        location = re.match(
            r"^(?P<file>.+):(?P<line>\d+):(?P<column>\d+):\s*(?P<message>.*)$",
            location_text,
        ) or re.match(r"^(?P<file>.+):(?P<line>\d+):\s*(?P<message>.*)$", location_text)
        if not location:
            continue
        file_text = location.group("file")
        line_text = location.group("line")
        column_text = location.group("column")
        message = location.group("message")

        severity = Severity.ERROR if severity_text == "Error" else Severity.WARNING
        findings.append(
            Finding(
                severity=severity,
                rule_id=rule_id or severity_text.upper(),
                message=message.strip(),
                file=Path(file_text),
                line=int(line_text),
                column=int(column_text) if column_text else None,
                tool="verilator",
            )
        )
    return findings


def parse_verible_lint(text: str) -> list[Finding]:
    findings = []
    for line in text.splitlines():
        match = VERIBLE_RE.match(line.strip())
        if not match:
            continue

        file_text, line_text, column_text, message, rule_id = match.groups()
        severity = Severity.ERROR if "error" in message.lower() else Severity.WARNING
        findings.append(
            Finding(
                severity=severity,
                rule_id=rule_id,
                message=message.strip(),
                file=Path(file_text),
                line=int(line_text),
                column=int(column_text),
                tool="verible",
            )
        )
    return findings


class LintStage:
    name: str
    tool_name: str

    def available(self) -> bool:
        return shutil.which(self.tool_name) is not None

    def command(self, cfg, root: Path) -> list[str]:
        raise NotImplementedError

    def parse(self, text: str) -> list[Finding]:
        raise NotImplementedError

    def run(self, cfg, ctx: RunContext, dry_run=False, root: Path | None = None) -> StageResult:
        root = root or Path.cwd()
        started = time.perf_counter()
        ctx.workdir.mkdir(parents=True, exist_ok=True)
        log_file = ctx.workdir / "lint.log"
        artifacts = {"log": log_file}
        cmd = self.command(cfg, root)
        command_text = "+ " + " ".join(str(arg) for arg in cmd)
        print(command_text)
        log_file.write_text(command_text + "\n")

        if dry_run:
            return StageResult(
                stage=self.name,
                status=Status.PASS,
                findings=[],
                artifacts=artifacts,
                duration_sec=time.perf_counter() - started,
            )

        if not self.available():
            finding = Finding(
                severity=Severity.INFO,
                rule_id="TOOL_MISSING",
                message=f"lint tool not available: {self.tool_name}",
                file=Path(cfg["sources"]),
                line=None,
                column=None,
                tool=self.tool_name,
            )
            return StageResult(
                stage=self.name,
                status=Status.SKIPPED,
                findings=[finding],
                artifacts=artifacts,
                duration_sec=time.perf_counter() - started,
            )

        result = subprocess.run(
            cmd,
            cwd=root,
            timeout=cfg["timeout_sec"],
            text=True,
            capture_output=True,
        )
        output = result.stdout + result.stderr
        if output:
            print(output, end="")
            with log_file.open("a") as f:
                f.write(output)

        findings = self.parse(output)
        if any(finding.severity is Severity.ERROR for finding in findings):
            status = Status.FAIL
        elif result.returncode == 0:
            status = Status.PASS
        else:
            status = Status.ERROR
            findings = [
                Finding(
                    severity=Severity.ERROR,
                    rule_id="LINT_ERROR",
                    message=f"{self.tool_name} exited with code {result.returncode}",
                    file=Path(cfg["sources"]),
                    line=None,
                    column=None,
                    tool=self.tool_name,
                )
            ]

        return StageResult(
            stage=self.name,
            status=status,
            findings=findings,
            artifacts=artifacts,
            duration_sec=time.perf_counter() - started,
        )


class VerilatorLintStage(LintStage):
    name = "lint_verilator"
    tool_name = "verilator"

    def command(self, cfg, root: Path) -> list[str]:
        cmd = [
            "verilator",
            "--lint-only",
            "--timing",
            "-Wno-fatal",
            "-Wall",
            "-f",
            cfg["sources"],
            "--top-module",
            cfg["top"],
        ]
        return cmd

    def parse(self, text: str) -> list[Finding]:
        return parse_verilator_lint(text)


class VeribleLintStage(LintStage):
    name = "lint_verible"
    tool_name = "verible-verilog-lint"

    def command(self, cfg, root: Path) -> list[str]:
        return [self.tool_name, *[str(path) for path in read_file_list(root, cfg["sources"])]]

    def parse(self, text: str) -> list[Finding]:
        return parse_verible_lint(text)
