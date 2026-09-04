from __future__ import annotations

import json
import re
from pathlib import Path


def latest_results_path(root: Path, block: str) -> Path | None:
    block_work = root / "work" / block
    if not block_work.exists():
        return None
    candidates = [
        path
        for path in block_work.glob("*/results.json")
        if "cache" not in path.parts
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def load_latest_results(root: Path, block: str) -> dict | None:
    path = latest_results_path(root, block)
    if path is None:
        return None
    return json.loads(path.read_text())


def normalize_message(message: str) -> str:
    message = re.sub(r"\b\d+\b", "<num>", message)
    return " ".join(message.split())


def finding_key(finding: dict) -> str:
    return "|".join(
        [
            finding.get("tool") or "",
            finding.get("rule_id") or "",
            finding.get("file") or "",
            normalize_message(finding.get("message") or ""),
        ]
    )


def result_finding_keys(results_doc: dict) -> set[str]:
    keys = set()
    for stage in results_doc.get("stages", []):
        for finding in stage.get("findings", []):
            keys.add(finding_key(finding))
    return keys


def save_baseline(root: Path, blocks: list[str]) -> Path:
    baseline = {"schema_version": 1, "blocks": {}}
    for block in blocks:
        results_doc = load_latest_results(root, block)
        if results_doc is None:
            continue
        baseline["blocks"][block] = {
            "run_id": results_doc.get("run_id"),
            "findings": sorted(result_finding_keys(results_doc)),
        }

    path = root / "work" / "baseline.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
    return path


def load_baseline(root: Path, name: str) -> dict:
    if name != "baseline":
        raise ValueError(f"unsupported baseline: {name}")
    path = root / "work" / "baseline.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


def compare_to_baseline(results_doc: dict, baseline: dict) -> dict:
    block = results_doc["block"]
    baseline_keys = set(baseline.get("blocks", {}).get(block, {}).get("findings", []))
    current_keys = result_finding_keys(results_doc)
    return {
        "new": sorted(current_keys - baseline_keys),
        "fixed": sorted(baseline_keys - current_keys),
        "unchanged": sorted(current_keys & baseline_keys),
    }
