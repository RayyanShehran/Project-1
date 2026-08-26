from rtlflow.cli import SIMULATORS, load_block_config
from rtlflow.cli import IcarusSimulator


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