from pathlib import Path

from rtlflow.checks import (
    ChecksStage,
    ModuleFilenameMatchCheck,
    NoBareAlwaysCheck,
    ResetPortNamingCheck,
    SourceText,
    strip_comments_and_strings,
)
from rtlflow.models import RunContext, Severity, Status


def source(path, text):
    return SourceText(
        file=Path(path),
        original=text,
        sanitized=strip_comments_and_strings(text),
    )


def test_no_bare_always_ignores_comments_and_strings():
    text = """
module demo;
  // always should not count in a comment
  string s = "always should not count in a string";
  always_ff @(posedge clk) begin end
  always @(posedge clk) begin end
endmodule
"""

    findings = NoBareAlwaysCheck().run(source("demo.sv", text), {})

    assert len(findings) == 1
    assert findings[0].line == 6


def test_reset_port_naming_uses_configurable_pattern():
    text = """
module counter(input logic clk, input logic rst_n);
endmodule
"""

    findings = ResetPortNamingCheck().run(
        source("counter.sv", text),
        {"pattern": r"^arst_n$", "severity": "warning"},
    )

    assert len(findings) == 1
    assert findings[0].severity is Severity.WARNING
    assert findings[0].rule_id == "reset-port-naming"


def test_module_filename_match_flags_mismatch_and_multiple_modules():
    text = """
module wrong;
endmodule
module second;
endmodule
"""

    findings = ModuleFilenameMatchCheck().run(source("right.sv", text), {})

    assert [finding.rule_id for finding in findings] == [
        "module-filename-match",
        "module-filename-match",
        "module-filename-match",
    ]
    assert "more than one module" in findings[0].message


def test_checks_stage_runs_enabled_rules(tmp_path):
    rtl = tmp_path / "demo.sv"
    rtl.write_text("module demo(input logic rst_n); always @(posedge clk) begin end endmodule\n")
    file_list = tmp_path / "files.f"
    file_list.write_text("demo.sv\n")
    cfg = {
        "sources": str(file_list),
        "checks": {
            "reset-port-naming": {"pattern": "^arst_n$"},
            "module-filename-match": {"enabled": False},
        },
    }

    result = ChecksStage().run(
        cfg,
        RunContext(run_id="checks", workdir=tmp_path / "work"),
        root=tmp_path,
    )

    assert result.status is Status.FAIL
    assert {finding.rule_id for finding in result.findings} == {
        "reset-port-naming",
        "no-bare-always",
    }
