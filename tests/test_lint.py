from pathlib import Path

from rtlflow.lint import (
    VeribleLintStage,
    VerilatorLintStage,
    parse_verible_lint,
    parse_verilator_lint,
    read_file_list,
)
from rtlflow.models import RunContext, Severity, Status


def test_parse_verilator_warning():
    text = "%Warning-WIDTH: blocks/fifo/rtl/fifo.sv:18:24: Operator ADD expects 32 bits"

    findings = parse_verilator_lint(text)

    assert len(findings) == 1
    assert findings[0].severity is Severity.WARNING
    assert findings[0].rule_id == "WIDTH"
    assert findings[0].file == Path("blocks/fifo/rtl/fifo.sv")
    assert findings[0].line == 18
    assert findings[0].column == 24


def test_parse_verilator_error_without_rule_id():
    text = "%Error: blocks/adder/rtl/adder.sv:3:1: syntax error"

    findings = parse_verilator_lint(text)

    assert len(findings) == 1
    assert findings[0].severity is Severity.ERROR
    assert findings[0].rule_id == "ERROR"
    assert findings[0].line == 3
    assert findings[0].column == 1


def test_parse_verilator_clean_output():
    assert parse_verilator_lint("") == []


def test_parse_verible_warning():
    text = "blocks/counter/rtl/counter.sv:5:24: Signal names must use lower_snake_case [signal-name-style]"

    findings = parse_verible_lint(text)

    assert len(findings) == 1
    assert findings[0].severity is Severity.WARNING
    assert findings[0].rule_id == "signal-name-style"
    assert findings[0].file == Path("blocks/counter/rtl/counter.sv")
    assert findings[0].line == 5
    assert findings[0].column == 24


def test_parse_verible_clean_output():
    assert parse_verible_lint("") == []


def test_read_file_list_resolves_relative_entries(tmp_path):
    file_list = tmp_path / "files.f"
    file_list.write_text("blocks/adder/rtl/adder.sv\n# comment\n\n")

    files = read_file_list(tmp_path, str(file_list))

    assert files == [tmp_path / "blocks/adder/rtl/adder.sv"]


def test_lint_stages_dry_run_without_tools(capsys, tmp_path):
    cfg = {
        "sources": str(tmp_path / "files.f"),
        "top": "adder_tb",
        "parameters": {"WIDTH": 8},
        "timeout_sec": 60,
    }
    Path(cfg["sources"]).write_text("blocks/adder/rtl/adder.sv\n")

    for stage in [VerilatorLintStage(), VeribleLintStage()]:
        ctx = RunContext(run_id=stage.name, workdir=tmp_path / stage.name)
        result = stage.run(cfg, ctx, dry_run=True, root=tmp_path)
        assert result.status is Status.PASS

    output = capsys.readouterr().out
    assert "verilator --lint-only" in output
    assert "verible-verilog-lint" in output
