from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from rtlflow.models import Finding


@dataclass(frozen=True)
class Waiver:
    rule: str
    file: Path
    line: int | None
    reason: str
    expires: date
    owner: str | None = None


@dataclass(frozen=True)
class WaiverAudit:
    active: list[Waiver]
    expired: list[Waiver]
    stale: list[Waiver]
    waived_findings: list[Finding]


def load_waivers(raw_waivers, config_path: Path) -> list[Waiver]:
    waivers = []
    for index, raw in enumerate(raw_waivers or [], start=1):
        for field in ["rule", "file", "reason", "expires"]:
            if not raw.get(field):
                raise ValueError(
                    f"{config_path} waiver #{index} missing required field: {field}"
                )

        try:
            expires = date.fromisoformat(str(raw["expires"]))
        except ValueError as e:
            raise ValueError(
                f"{config_path} waiver #{index} has invalid expires date: {raw['expires']}"
            ) from e

        waivers.append(
            Waiver(
                rule=str(raw["rule"]),
                file=Path(str(raw["file"])),
                line=int(raw["line"]) if raw.get("line") is not None else None,
                reason=str(raw["reason"]),
                expires=expires,
                owner=str(raw["owner"]) if raw.get("owner") is not None else None,
            )
        )
    return waivers


def paths_match(waiver_file: Path, finding_file: Path) -> bool:
    waiver_text = waiver_file.as_posix()
    finding_text = finding_file.as_posix()
    return finding_text == waiver_text or finding_text.endswith("/" + waiver_text)


def waiver_matches(waiver: Waiver, finding: Finding) -> bool:
    if waiver.rule != finding.rule_id:
        return False
    if not paths_match(waiver.file, finding.file):
        return False
    return waiver.line is None or waiver.line == finding.line


def audit_waivers(
    waivers: list[Waiver],
    findings: list[Finding],
    today: date | None = None,
) -> WaiverAudit:
    today = today or date.today()
    active = []
    expired = []
    stale = []
    waived_findings = []

    for waiver in waivers:
        if waiver.expires < today:
            expired.append(waiver)
            continue

        matches = [finding for finding in findings if waiver_matches(waiver, finding)]
        if matches:
            active.append(waiver)
            waived_findings.extend(matches)
        else:
            stale.append(waiver)

    return WaiverAudit(
        active=active,
        expired=expired,
        stale=stale,
        waived_findings=waived_findings,
    )


def apply_waivers(
    findings: list[Finding],
    waivers: list[Waiver],
    today: date | None = None,
) -> tuple[list[Finding], WaiverAudit]:
    audit = audit_waivers(waivers, findings, today)
    waived = set(audit.waived_findings)
    return [finding for finding in findings if finding not in waived], audit
