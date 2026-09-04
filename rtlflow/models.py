from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Status(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    CACHED = "CACHED"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    rule_id: str
    message: str
    file: Path
    line: int | None
    column: int | None
    tool: str


@dataclass
class StageResult:
    stage: str
    status: Status
    findings: list[Finding]
    artifacts: dict[str, Path]
    duration_sec: float


@dataclass
class RunContext:
    run_id: str
    workdir: Path
    artifacts: dict[str, Path] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
