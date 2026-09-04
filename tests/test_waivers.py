from datetime import date
from pathlib import Path

import pytest

from rtlflow.models import Finding, Severity
from rtlflow.waivers import apply_waivers, load_waivers


def make_finding(rule="WIDTHTRUNC", line=42):
    return Finding(
        severity=Severity.WARNING,
        rule_id=rule,
        message="width mismatch",
        file=Path("blocks/fifo/rtl/fifo.sv"),
        line=line,
        column=7,
        tool="verilator",
    )


def test_load_waiver_requires_reason_and_expiry(tmp_path):
    with pytest.raises(ValueError, match="reason"):
        load_waivers(
            [
                {
                    "rule": "WIDTHTRUNC",
                    "file": "rtl/fifo.sv",
                    "expires": "2026-12-31",
                }
            ],
            tmp_path / "block.yaml",
        )

    with pytest.raises(ValueError, match="expires"):
        load_waivers(
            [
                {
                    "rule": "WIDTHTRUNC",
                    "file": "rtl/fifo.sv",
                    "reason": "known issue",
                }
            ],
            tmp_path / "block.yaml",
        )


def test_apply_waivers_suppresses_matching_finding():
    waivers = load_waivers(
        [
            {
                "rule": "WIDTHTRUNC",
                "file": "rtl/fifo.sv",
                "line": 42,
                "reason": "upper bits are bounded by DEPTH",
                "expires": "2026-12-31",
                "owner": "hamza",
            }
        ],
        Path("block.yaml"),
    )

    remaining, audit = apply_waivers(
        [make_finding()],
        waivers,
        today=date(2026, 9, 4),
    )

    assert remaining == []
    assert len(audit.waived_findings) == 1
    assert audit.stale == []
    assert audit.expired == []


def test_file_wide_waiver_matches_any_line():
    waivers = load_waivers(
        [
            {
                "rule": "WIDTHTRUNC",
                "file": "rtl/fifo.sv",
                "reason": "existing generated code",
                "expires": "2026-12-31",
            }
        ],
        Path("block.yaml"),
    )

    remaining, audit = apply_waivers(
        [make_finding(line=10), make_finding(line=20)],
        waivers,
        today=date(2026, 9, 4),
    )

    assert remaining == []
    assert len(audit.waived_findings) == 2


def test_expired_waiver_is_reported_and_not_applied():
    waivers = load_waivers(
        [
            {
                "rule": "WIDTHTRUNC",
                "file": "rtl/fifo.sv",
                "reason": "temporary exception",
                "expires": "2026-01-01",
            }
        ],
        Path("block.yaml"),
    )

    remaining, audit = apply_waivers(
        [make_finding()],
        waivers,
        today=date(2026, 9, 4),
    )

    assert remaining == [make_finding()]
    assert len(audit.expired) == 1


def test_stale_waiver_is_reported_when_it_matches_nothing():
    waivers = load_waivers(
        [
            {
                "rule": "UNUSED",
                "file": "rtl/fifo.sv",
                "reason": "old issue",
                "expires": "2026-12-31",
            }
        ],
        Path("block.yaml"),
    )

    remaining, audit = apply_waivers(
        [make_finding()],
        waivers,
        today=date(2026, 9, 4),
    )

    assert remaining == [make_finding()]
    assert len(audit.stale) == 1
