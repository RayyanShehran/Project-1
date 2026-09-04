from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from rtlflow.lint import read_file_list
from rtlflow.models import Finding, RunContext, Severity, StageResult, Status


IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")


@dataclass(frozen=True)
class SourceText:
    file: Path
    original: str
    sanitized: str

    def line_column(self, offset: int) -> tuple[int, int]:
        line = self.sanitized.count("\n", 0, offset) + 1
        line_start = self.sanitized.rfind("\n", 0, offset)
        column = offset + 1 if line_start == -1 else offset - line_start
        return line, column


class Check(Protocol):
    rule_id: str
    description: str
    default_severity: Severity

    def run(self, source: SourceText, config: dict) -> list[Finding]:
        ...


def strip_comments_and_strings(text: str) -> str:
    chars = list(text)
    index = 0
    state = "code"
    while index < len(chars):
        current = chars[index]
        nxt = chars[index + 1] if index + 1 < len(chars) else ""

        if state == "code" and current == "/" and nxt == "/":
            chars[index] = chars[index + 1] = " "
            index += 2
            state = "line_comment"
            continue
        if state == "code" and current == "/" and nxt == "*":
            chars[index] = chars[index + 1] = " "
            index += 2
            state = "block_comment"
            continue
        if state == "code" and current == '"':
            chars[index] = " "
            index += 1
            state = "string"
            continue

        if state == "line_comment":
            if current == "\n":
                state = "code"
            else:
                chars[index] = " "
            index += 1
            continue

        if state == "block_comment":
            if current == "*" and nxt == "/":
                chars[index] = chars[index + 1] = " "
                index += 2
                state = "code"
            else:
                if current != "\n":
                    chars[index] = " "
                index += 1
            continue

        if state == "string":
            if current == "\\":
                chars[index] = " "
                if index + 1 < len(chars) and chars[index + 1] != "\n":
                    chars[index + 1] = " "
                    index += 2
                else:
                    index += 1
                continue
            if current == '"':
                chars[index] = " "
                state = "code"
            elif current != "\n":
                chars[index] = " "
            index += 1
            continue

        index += 1
    return "".join(chars)


def configured_severity(config: dict, default: Severity) -> Severity:
    value = config.get("severity")
    return Severity(value) if value else default


def enabled(config: dict) -> bool:
    return config.get("enabled", True)


class ResetPortNamingCheck:
    rule_id = "reset-port-naming"
    description = "Reset ports must match the configured reset naming pattern"
    default_severity = Severity.ERROR

    def run(self, source: SourceText, config: dict) -> list[Finding]:
        if not enabled(config):
            return []
        pattern = re.compile(config.get("pattern", r"^arst_n$"))
        severity = configured_severity(config, self.default_severity)
        findings = []
        for line_number, line in enumerate(source.sanitized.splitlines(), start=1):
            for declaration in re.finditer(r"\b(?:input|inout)\b([^,;)]*)", line):
                identifiers = IDENT_RE.findall(declaration.group(1))
                if not identifiers:
                    continue
                name = identifiers[-1]
                if not re.search(r"rst|reset", name, re.IGNORECASE):
                    continue
                if pattern.fullmatch(name):
                    continue
                column = line.find(name, declaration.start()) + 1
                findings.append(
                    Finding(
                        severity=severity,
                        rule_id=self.rule_id,
                        message=f"reset port '{name}' does not match required pattern '{pattern.pattern}'",
                        file=source.file,
                        line=line_number,
                        column=column,
                        tool="checks",
                    )
                )
        return findings


class NoBareAlwaysCheck:
    rule_id = "no-bare-always"
    description = "Use always_ff, always_comb, or always_latch instead of bare always"
    default_severity = Severity.ERROR

    def run(self, source: SourceText, config: dict) -> list[Finding]:
        if not enabled(config):
            return []
        severity = configured_severity(config, self.default_severity)
        findings = []
        for match in re.finditer(r"\balways\b", source.sanitized):
            tail = source.sanitized[match.end() : match.end() + 16]
            if tail.startswith("_ff") or tail.startswith("_comb") or tail.startswith("_latch"):
                continue
            line, column = source.line_column(match.start())
            findings.append(
                Finding(
                    severity=severity,
                    rule_id=self.rule_id,
                    message="bare always block; use always_ff, always_comb, or always_latch",
                    file=source.file,
                    line=line,
                    column=column,
                    tool="checks",
                )
            )
        return findings


class ModuleFilenameMatchCheck:
    rule_id = "module-filename-match"
    description = "A file should contain one module whose name matches the file stem"
    default_severity = Severity.ERROR

    def run(self, source: SourceText, config: dict) -> list[Finding]:
        if not enabled(config):
            return []
        severity = configured_severity(config, self.default_severity)
        findings = []
        modules = [
            (match.group(1), *source.line_column(match.start(1)))
            for match in re.finditer(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)", source.sanitized)
        ]
        if len(modules) > 1:
            line, column = modules[1][1], modules[1][2]
            findings.append(
                Finding(
                    severity=severity,
                    rule_id=self.rule_id,
                    message="file contains more than one module",
                    file=source.file,
                    line=line,
                    column=column,
                    tool="checks",
                )
            )
        for module_name, line, column in modules:
            if module_name != source.file.stem:
                findings.append(
                    Finding(
                        severity=severity,
                        rule_id=self.rule_id,
                        message=f"module '{module_name}' does not match file name '{source.file.stem}'",
                        file=source.file,
                        line=line,
                        column=column,
                        tool="checks",
                    )
                )
        return findings


CHECKS = {
    check.rule_id: check
    for check in [
        ResetPortNamingCheck(),
        NoBareAlwaysCheck(),
        ModuleFilenameMatchCheck(),
    ]
}


class ChecksStage:
    name = "checks"

    def available(self):
        return True

    def run(self, cfg, ctx: RunContext, dry_run=False, root: Path | None = None) -> StageResult:
        root = root or Path.cwd()
        started = time.perf_counter()
        ctx.workdir.mkdir(parents=True, exist_ok=True)
        findings = []
        check_config = cfg.get("checks", {})
        for file in read_file_list(root, cfg["sources"]):
            if dry_run:
                continue
            text = file.read_text()
            source = SourceText(
                file=file,
                original=text,
                sanitized=strip_comments_and_strings(text),
            )
            for rule_id, check in CHECKS.items():
                findings.extend(check.run(source, check_config.get(rule_id, {})))

        status = Status.FAIL if findings else Status.PASS
        return StageResult(
            stage=self.name,
            status=status,
            findings=findings,
            artifacts={},
            duration_sec=time.perf_counter() - started,
        )
