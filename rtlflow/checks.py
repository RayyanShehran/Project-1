from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol

from rtlflow.lint import read_file_list
from rtlflow.models import Finding, RunContext, Severity, StageResult, Status
from rtlflow.syntax import SyntaxTree, parse_syntax_file, strip_comments_and_strings


class Check(Protocol):
    rule_id: str
    description: str
    default_severity: Severity

    def run(self, tree: SyntaxTree, config: dict) -> list[Finding]:
        ...


def configured_severity(config: dict, default: Severity) -> Severity:
    value = config.get("severity")
    return Severity(value) if value else default


def enabled(config: dict) -> bool:
    return config.get("enabled", True)


class ResetPortNamingCheck:
    rule_id = "reset-port-naming"
    description = "Reset ports must match the configured reset naming pattern"
    default_severity = Severity.ERROR

    def run(self, tree: SyntaxTree, config: dict) -> list[Finding]:
        if not enabled(config):
            return []
        import re

        pattern = re.compile(config.get("pattern", r"^arst_n$"))
        severity = configured_severity(config, self.default_severity)
        findings = []
        for port in tree.find_all("PortDeclaration"):
            if port.attrs.get("direction") not in {"input", "inout"}:
                continue
            name = port.attrs["name"]
            if not re.search(r"rst|reset", name, re.IGNORECASE):
                continue
            if pattern.fullmatch(name):
                continue
            findings.append(
                Finding(
                    severity=severity,
                    rule_id=self.rule_id,
                    message=f"reset port '{name}' does not match required pattern '{pattern.pattern}'",
                    file=tree.file,
                    line=port.line,
                    column=port.column,
                    tool="checks",
                )
            )
        return findings


class NoBareAlwaysCheck:
    rule_id = "no-bare-always"
    description = "Use always_ff, always_comb, or always_latch instead of bare always"
    default_severity = Severity.ERROR

    def run(self, tree: SyntaxTree, config: dict) -> list[Finding]:
        if not enabled(config):
            return []
        severity = configured_severity(config, self.default_severity)
        findings = []
        for always in tree.find_all("AlwaysConstruct"):
            if always.attrs.get("variant") != "bare":
                continue
            findings.append(
                Finding(
                    severity=severity,
                    rule_id=self.rule_id,
                    message="bare always block; use always_ff, always_comb, or always_latch",
                    file=tree.file,
                    line=always.line,
                    column=always.column,
                    tool="checks",
                )
            )
        return findings


class ModuleFilenameMatchCheck:
    rule_id = "module-filename-match"
    description = "A file should contain one module whose name matches the file stem"
    default_severity = Severity.ERROR

    def run(self, tree: SyntaxTree, config: dict) -> list[Finding]:
        if not enabled(config):
            return []
        severity = configured_severity(config, self.default_severity)
        findings = []
        modules = tree.find_all("ModuleDeclaration")
        if len(modules) > 1:
            findings.append(
                Finding(
                    severity=severity,
                    rule_id=self.rule_id,
                    message="file contains more than one module",
                    file=tree.file,
                    line=modules[1].line,
                    column=modules[1].column,
                    tool="checks",
                )
            )
        for module in modules:
            module_name = module.attrs["name"]
            if module_name != tree.file.stem:
                findings.append(
                    Finding(
                        severity=severity,
                        rule_id=self.rule_id,
                        message=f"module '{module_name}' does not match file name '{tree.file.stem}'",
                        file=tree.file,
                        line=module.line,
                        column=module.column,
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


def should_check_file(file: Path, config: dict) -> bool:
    scope = config.get("scope", "rtl")
    if scope == "all":
        return True
    return "/rtl/" in file.as_posix()


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
            if not should_check_file(file, check_config):
                continue
            if dry_run:
                continue
            tree = parse_syntax_file(file)
            for rule_id, check in CHECKS.items():
                findings.extend(check.run(tree, check_config.get(rule_id, {})))

        status = Status.FAIL if findings else Status.PASS
        return StageResult(
            stage=self.name,
            status=status,
            findings=findings,
            artifacts={},
            duration_sec=time.perf_counter() - started,
        )
