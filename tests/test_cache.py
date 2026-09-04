from pathlib import Path

from rtlflow.cache import (
    compute_input_hash,
    load_cached_results,
    materialize_cached_results,
    save_cached_results,
)


def make_project(tmp_path):
    block_dir = tmp_path / "blocks" / "adder"
    block_dir.mkdir(parents=True)
    rtl = block_dir / "adder.sv"
    rtl.write_text("module adder; endmodule\n")
    files = block_dir / "files.f"
    files.write_text("blocks/adder/adder.sv\n")
    (block_dir / "block.yaml").write_text("name: adder\nsources: files.f\n")
    (tmp_path / "rtlflow.yaml").write_text("flows: {}\n")
    return {
        "name": "adder",
        "sources": str(files),
    }


def test_input_hash_changes_when_source_changes(tmp_path):
    cfg = make_project(tmp_path)
    project_config = {"flows": {"quick": ["checks"]}, "checks": {}}

    before = compute_input_hash(tmp_path, cfg, "quick", project_config, {"verilator": None})
    (tmp_path / "blocks" / "adder" / "adder.sv").write_text("module changed; endmodule\n")
    after = compute_input_hash(tmp_path, cfg, "quick", project_config, {"verilator": None})

    assert before != after


def test_cached_results_are_marked_and_materialized(tmp_path):
    data = {
        "status": "PASS",
        "stages": [{"stage": "checks", "status": "PASS", "duration_sec": 1.2}],
    }
    save_cached_results(tmp_path, "abc", data)

    cached = load_cached_results(tmp_path, "abc")
    path = materialize_cached_results(cached, tmp_path / "work" / "adder" / "run-1")

    assert cached["cached"] is True
    assert cached["stages"][0]["status"] == "CACHED"
    assert path == tmp_path / "work" / "adder" / "run-1" / "results.json"
