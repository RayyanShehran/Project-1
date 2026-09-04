from pathlib import Path

from rtlflow.adopt import (
    find_source_files,
    infer_adoption,
    instantiated_modules,
    module_names,
    write_adopted_config,
)


def test_find_source_files_prefers_file_list(tmp_path):
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    source = rtl / "decoder.sv"
    source.write_text("module decoder; endmodule\n")
    file_list = tmp_path / "sources.f"
    file_list.write_text("rtl/decoder.sv\n")

    sources, discovered_file_list = find_source_files(tmp_path)

    assert sources == [source]
    assert discovered_file_list == file_list


def test_module_and_instantiation_extraction_ignores_comments():
    text = """
// module fake;
module decoder; endmodule
module decoder_tb;
  decoder dut();
endmodule
"""

    modules = module_names(text)
    instantiated = instantiated_modules(text, set(modules))

    assert modules == ["decoder", "decoder_tb"]
    assert instantiated == {"decoder"}


def test_infer_adoption_reports_ambiguous_top(tmp_path):
    (tmp_path / "a.sv").write_text("module a; endmodule\n")
    (tmp_path / "b.sv").write_text("module b; endmodule\n")

    adopted = infer_adoption(tmp_path)

    assert adopted.ambiguous is True
    assert adopted.top_candidates == ["a", "b"]


def test_infer_adoption_detects_testbench_and_writes_config(tmp_path):
    (tmp_path / "decoder.sv").write_text("module decoder; endmodule\n")
    (tmp_path / "decoder_tb.sv").write_text("module decoder_tb; decoder dut(); endmodule\n")
    (tmp_path / "defs.svh").write_text("`define WIDTH 8\n")

    adopted = infer_adoption(tmp_path)
    output = write_adopted_config(adopted, tmp_path / "out" / "block.yaml", tmp_path)

    assert adopted.testbench == "decoder_tb"
    assert adopted.top == "decoder_tb"
    assert output.read_text().startswith("name: decoder")
    assert (tmp_path / "out" / "files.f").read_text().count(".sv") == 2
