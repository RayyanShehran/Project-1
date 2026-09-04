from pathlib import Path

from rtlflow.syntax import parse_syntax_text, strip_comments_and_strings


def test_syntax_tree_extracts_modules_ports_always_and_instantiations():
    text = """
module child(input logic clk);
endmodule

module top(input logic clk, input logic arst_n, output logic done);
  child #(.WIDTH(8)) u_child(.clk(clk));
  always_ff @(posedge clk or negedge arst_n) begin end
  always_comb begin end
endmodule
"""

    tree = parse_syntax_text(Path("top.sv"), text)

    modules = tree.find_all("ModuleDeclaration")
    ports = tree.find_all("PortDeclaration")
    always_blocks = tree.find_all("AlwaysConstruct")
    instantiations = tree.find_all("ModuleInstantiation")

    assert [module.attrs["name"] for module in modules] == ["child", "top"]
    assert [port.attrs["name"] for port in ports] == ["clk", "clk", "arst_n", "done"]
    assert [always.attrs["variant"] for always in always_blocks] == ["ff", "comb"]
    assert [(inst.attrs["module"], inst.attrs["instance"]) for inst in instantiations] == [
        ("child", "u_child")
    ]


def test_syntax_tree_ignores_comments_and_strings():
    text = """
// module fake(input logic rst_n); always @(posedge clk); endmodule
module demo(input logic clk);
  string s = "module nope; always @(posedge clk); endmodule";
endmodule
"""

    tree = parse_syntax_text(Path("demo.sv"), text)

    assert [module.attrs["name"] for module in tree.find_all("ModuleDeclaration")] == ["demo"]
    assert tree.find_all("AlwaysConstruct") == []


def test_strip_comments_and_strings_preserves_line_numbers():
    text = 'module demo;\n  string s = "always"; // always\n  always_ff begin end\nendmodule\n'

    sanitized = strip_comments_and_strings(text)

    assert sanitized.count("\n") == text.count("\n")
    assert "always_ff" in sanitized
    assert '"always"' not in sanitized


def test_parse_syntax_text_preserves_verible_json():
    tree = parse_syntax_text(Path("demo.sv"), "module demo; endmodule\n", verible_json={"tree": []})

    assert tree.verible_json == {"tree": []}
