from rtlflow.cli import SIMULATORS, load_block_config
from rtlflow.cli import IcarusSimulator, VerilatorSimulator
import pytest


@pytest.mark.integration
def test_icarus_integration():
    cfg = load_block_config("adder")
    cfg["work_dir"] = cfg["base_work_dir"] / "icarus"
    cfg["work_dir"].mkdir(parents=True, exist_ok=True)
    cfg["vvp_file"] = cfg["work_dir"] / "sim.vvp"
    cfg["waveform"] = cfg["work_dir"] / "waveform.vcd"
    cfg["log_file"] = cfg["work_dir"] / "run.log"

    sim = IcarusSimulator()

    if not sim.available():
        pytest.skip("Icarus is not installed")

    sim.build(cfg)
    sim.run(cfg)


@pytest.mark.integration
def test_verilator_integration():
    cfg = load_block_config("adder")
    cfg["work_dir"] = cfg["base_work_dir"] / "verilator"
    cfg["work_dir"].mkdir(parents=True, exist_ok=True)
    cfg["vvp_file"] = cfg["work_dir"] / "sim.vvp"
    cfg["waveform"] = cfg["work_dir"] / "waveform.vcd"
    cfg["log_file"] = cfg["work_dir"] / "run.log"

    sim = VerilatorSimulator()

    if not sim.available():
        pytest.skip("Verilator is not installed")

    sim.build(cfg)
    sim.run(cfg)


def test_verilator_dry_run_prints_expected_commands(capsys):
    cfg = load_block_config("adder")
    cfg["work_dir"] = cfg["base_work_dir"] / "verilator"
    cfg["work_dir"].mkdir(parents=True, exist_ok=True)
    cfg["vvp_file"] = cfg["work_dir"] / "sim.vvp"
    cfg["waveform"] = cfg["work_dir"] / "waveform.vcd"
    cfg["log_file"] = cfg["work_dir"] / "run.log"

    sim = VerilatorSimulator()
    sim.build(cfg, dry_run=True)
    sim.run(cfg, dry_run=True)

    output = capsys.readouterr().out

    assert "verilator" in output
    assert "--binary" in output
    assert "--timing" in output
    assert "--trace" in output
    assert "--top-module adder_tb" in output
    assert "/tmp/rtlflow_adder_obj/Vadder_tb" in output


def test_icarus_dry_run_prints_expected_commands(capsys):
    cfg = load_block_config("adder")
    cfg["work_dir"] = cfg["base_work_dir"] / "icarus"
    cfg["work_dir"].mkdir(parents=True, exist_ok=True)
    cfg["vvp_file"] = cfg["work_dir"] / "sim.vvp"
    cfg["waveform"] = cfg["work_dir"] / "waveform.vcd"
    cfg["log_file"] = cfg["work_dir"] / "run.log"

    sim = IcarusSimulator()
    sim.build(cfg, dry_run=True)
    sim.run(cfg, dry_run=True)

    output = capsys.readouterr().out

    assert "iverilog" in output
    assert "-g2012" in output
    assert "blocks/adder/files.f" in output
    assert "vvp" in output


def test_simulators_registered():
    assert "icarus" in SIMULATORS
    assert "verilator" in SIMULATORS


def test_load_adder_config():
    cfg = load_block_config("adder")

    assert cfg["name"] == "adder"
    assert cfg["top"] == "adder_tb"
    assert cfg["timeout_sec"] == 60
    assert cfg["sources"].endswith("blocks/adder/files.f")