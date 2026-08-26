from rtlflow.cli import SIMULATORS, load_block_config


def test_simulators_registered():
    assert "icarus" in SIMULATORS
    assert "verilator" in SIMULATORS


def test_load_adder_config():
    cfg = load_block_config("adder")

    assert cfg["name"] == "adder"
    assert cfg["top"] == "adder_tb"
    assert cfg["timeout_sec"] == 60
    assert cfg["sources"].endswith("blocks/adder/files.f")