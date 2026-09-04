import json
from pathlib import Path

from rtlflow.baseline import (
    compare_to_baseline,
    finding_key,
    latest_results_path,
    normalize_message,
    save_baseline,
)


def result(block, run_id, findings):
    return {
        "block": block,
        "run_id": run_id,
        "stages": [{"stage": "checks", "findings": findings}],
    }


def finding(rule, message="bad signal", line=10):
    return {
        "tool": "checks",
        "rule_id": rule,
        "file": "blocks/adder/rtl/adder.sv",
        "line": line,
        "column": 1,
        "message": message,
    }


def test_finding_key_ignores_line_number_but_keeps_rule_file_and_message():
    first = finding_key(finding("reset-port-naming", line=10))
    second = finding_key(finding("reset-port-naming", line=20))
    other = finding_key(finding("no-bare-always", line=10))

    assert first == second
    assert first != other


def test_normalize_message_removes_numeric_noise():
    assert normalize_message("width 8 got 16") == "width <num> got <num>"


def test_save_baseline_from_latest_results(tmp_path):
    old = tmp_path / "work" / "adder" / "old"
    new = tmp_path / "work" / "adder" / "new"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    (old / "results.json").write_text(json.dumps(result("adder", "old", [])))
    (new / "results.json").write_text(
        json.dumps(result("adder", "new", [finding("no-bare-always")]))
    )

    assert latest_results_path(tmp_path, "adder") == new / "results.json"

    path = save_baseline(tmp_path, ["adder"])
    data = json.loads(path.read_text())

    assert data["blocks"]["adder"]["run_id"] == "new"
    assert len(data["blocks"]["adder"]["findings"]) == 1


def test_compare_to_baseline_classifies_changes():
    baseline = {
        "blocks": {
            "adder": {
                "findings": [
                    finding_key(finding("old")),
                    finding_key(finding("unchanged")),
                ]
            }
        }
    }
    current = result("adder", "run-2", [finding("new"), finding("unchanged")])

    comparison = compare_to_baseline(current, baseline)

    assert len(comparison["new"]) == 1
    assert len(comparison["fixed"]) == 1
    assert len(comparison["unchanged"]) == 1
