from pathlib import Path

import pytest

from rtlflow.cli import (
    SIMULATORS,
    IcarusSimulator,
    VerilatorSimulator,
    classify_output,
    load_block_config,
)

GOLDEN_DIR = Path(__file__).parent / "golden"


def normalize_path_text(text):
    return text.replace("\\", "/")


def make_cfg(block, sim_name):
    cfg = load_block_config(block)
    cfg["work_dir"] = cfg["base_work_dir"] / sim_name
    cfg["work_dir"].mkdir(parents=True, exist_ok=True)
    cfg["vvp_file"] = cfg["work_dir"] / "sim.vvp"
    cfg["waveform"] = cfg["work_dir"] / "waveform.vcd"
    cfg["log_file"] = cfg["work_dir"] / "run.log"
    return cfg


def test_classify_icarus_success():
    text = (GOLDEN_DIR / "success_icarus.txt").read_text()
    assert classify_output(text) == "Success"


def test_classify_icarus_compile_error():
    text = (GOLDEN_DIR / "compile_error_icarus.txt").read_text()
    assert classify_output(text) == "CompileError"


def test_classify_icarus_elaboration_error():
    text = (GOLDEN_DIR / "elaboration_error_icarus.txt").read_text()
    assert classify_output(text) == "ElaborationError"


def test_classify_simulation_failed():
    text = (GOLDEN_DIR / "simulation_failed.txt").read_text()
    assert classify_output(text) == "SimulationFailed"


def test_simulators_registered():
    assert "icarus" in SIMULATORS
    assert "verilator" in SIMULATORS


def test_load_adder_config():
    cfg = load_block_config("adder")

    assert cfg["name"] == "adder"
    assert cfg["top"] == "adder_tb"
    assert cfg["timeout_sec"] == 60
    assert cfg["parameters"] == {"WIDTH": 8}
    assert normalize_path_text(cfg["sources"]).endswith("blocks/adder/files.f")


def test_load_fifo_config():
    cfg = load_block_config("fifo")

    assert cfg["name"] == "fifo"
    assert cfg["top"] == "fifo_tb"
    assert cfg["timeout_sec"] == 60
    assert cfg["parameters"] == {"WIDTH": 8, "DEPTH": 4}
    assert normalize_path_text(cfg["sources"]).endswith("blocks/fifo/files.f")


def test_icarus_dry_run_prints_expected_commands(capsys):
    cfg = make_cfg("adder", "icarus")

    sim = IcarusSimulator()
    sim.build(cfg, dry_run=True)
    sim.run(cfg, dry_run=True)

    output = normalize_path_text(capsys.readouterr().out)

    assert "iverilog" in output
    assert "-g2012" in output
    assert "blocks/adder/files.f" in output
    assert "-P WIDTH=8" in output
    assert "vvp" in output


def test_verilator_dry_run_prints_expected_commands(capsys):
    cfg = make_cfg("adder", "verilator")

    sim = VerilatorSimulator()
    sim.build(cfg, dry_run=True)
    sim.run(cfg, dry_run=True)

    output = normalize_path_text(capsys.readouterr().out)

    assert "verilator" in output
    assert "--binary" in output
    assert "--timing" in output
    assert "--trace" in output
    assert "--top-module adder_tb" in output
    assert "-GWIDTH=8" in output
    assert "/tmp/rtlflow_adder_obj/Vadder_tb" in output


def test_icarus_fifo_dry_run_prints_expected_commands(capsys):
    cfg = make_cfg("fifo", "icarus")

    sim = IcarusSimulator()
    sim.build(cfg, dry_run=True)
    sim.run(cfg, dry_run=True)

    output = normalize_path_text(capsys.readouterr().out)

    assert "iverilog" in output
    assert "blocks/fifo/files.f" in output
    assert "-P WIDTH=8" in output
    assert "-P DEPTH=4" in output
    assert "vvp" in output


def test_verilator_fifo_dry_run_prints_expected_commands(capsys):
    cfg = make_cfg("fifo", "verilator")

    sim = VerilatorSimulator()
    sim.build(cfg, dry_run=True)
    sim.run(cfg, dry_run=True)

    output = normalize_path_text(capsys.readouterr().out)

    assert "verilator" in output
    assert "blocks/fifo/files.f" in output
    assert "--top-module fifo_tb" in output
    assert "-GWIDTH=8" in output
    assert "-GDEPTH=4" in output
    assert "/tmp/rtlflow_fifo_obj/Vfifo_tb" in output


@pytest.mark.integration
def test_icarus_integration():
    cfg = make_cfg("adder", "icarus")
    sim = IcarusSimulator()

    if not sim.available():
        pytest.skip("Icarus is not installed")

    sim.build(cfg)
    sim.run(cfg)


@pytest.mark.integration
def test_verilator_integration():
    cfg = make_cfg("adder", "verilator")
    sim = VerilatorSimulator()

    if not sim.available():
        pytest.skip("Verilator is not installed")

    sim.build(cfg)
    sim.run(cfg)


@pytest.mark.integration
def test_fifo_icarus_integration():
    cfg = make_cfg("fifo", "icarus")
    sim = IcarusSimulator()

    if not sim.available():
        pytest.skip("Icarus is not installed")

    sim.build(cfg)
    sim.run(cfg)


@pytest.mark.integration
def test_fifo_verilator_integration():
    cfg = make_cfg("fifo", "verilator")
    sim = VerilatorSimulator()

    if not sim.available():
        pytest.skip("Verilator is not installed")

    sim.build(cfg)
    sim.run(cfg)
