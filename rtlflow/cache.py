from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

from rtlflow.lint import read_file_list


def hash_bytes(digest, label: str, data: bytes):
    digest.update(label.encode())
    digest.update(b"\0")
    digest.update(data)
    digest.update(b"\0")


def file_bytes(path: Path) -> bytes:
    return path.read_bytes() if path.exists() else b""


def compute_input_hash(root: Path, cfg: dict, flow: str, project_config: dict, tools: dict) -> str:
    digest = hashlib.sha256()
    source_files = read_file_list(root, cfg["sources"])
    paths = [
        root / "rtlflow.yaml",
        root / "blocks" / cfg["name"] / "block.yaml",
        Path(cfg["sources"]),
        *source_files,
    ]
    for path in sorted(paths, key=lambda item: item.as_posix()):
        hash_bytes(digest, path.as_posix(), file_bytes(path))

    extra = {
        "block": cfg["name"],
        "flow": flow,
        "flow_config": project_config.get("flows", {}).get(flow),
        "checks": project_config.get("checks", {}),
        "tools": tools,
    }
    hash_bytes(digest, "config", json.dumps(extra, sort_keys=True).encode())
    return digest.hexdigest()


def cache_results_path(root: Path, input_hash: str) -> Path:
    return root / "work" / "cache" / input_hash / "results.json"


def load_cached_results(root: Path, input_hash: str) -> dict | None:
    path = cache_results_path(root, input_hash)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    cached = copy.deepcopy(data)
    cached["cached"] = True
    for stage in cached.get("stages", []):
        stage["status"] = "CACHED"
        stage["duration_sec"] = 0.0
    return cached


def save_cached_results(root: Path, input_hash: str, results_doc: dict) -> Path:
    path = cache_results_path(root, input_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = copy.deepcopy(results_doc)
    data["input_hash"] = input_hash
    data["cached"] = False
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return path


def materialize_cached_results(cached_doc: dict, workdir: Path) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / "results.json"
    path.write_text(json.dumps(cached_doc, indent=2, sort_keys=True) + "\n")
    return path


def clear_cache(root: Path) -> bool:
    cache_dir = root / "work" / "cache"
    if not cache_dir.exists():
        return False
    shutil.rmtree(cache_dir)
    return True
