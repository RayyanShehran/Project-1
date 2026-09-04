from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")


@dataclass(frozen=True)
class SyntaxNode:
    kind: str
    text: str
    line: int | None = None
    column: int | None = None
    attrs: dict = field(default_factory=dict)
    children: tuple["SyntaxNode", ...] = ()


@dataclass(frozen=True)
class SyntaxTree:
    file: Path
    source: str
    sanitized: str
    root: SyntaxNode
    verible_json: dict | None = None

    def find_all(self, kind: str, node: SyntaxNode | None = None) -> list[SyntaxNode]:
        node = node or self.root
        found = [node] if node.kind == kind else []
        for child in node.children:
            found.extend(self.find_all(kind, child))
        return found

    def find_children(self, node: SyntaxNode, kind: str) -> list[SyntaxNode]:
        return [child for child in node.children if child.kind == kind]

    def line_column(self, offset: int) -> tuple[int, int]:
        line = self.sanitized.count("\n", 0, offset) + 1
        line_start = self.sanitized.rfind("\n", 0, offset)
        column = offset + 1 if line_start == -1 else offset - line_start
        return line, column

    def identifier_text(self, node: SyntaxNode) -> str | None:
        return node.attrs.get("name")


def strip_comments_and_strings(text: str) -> str:
    chars = list(text)
    index = 0
    state = "code"
    while index < len(chars):
        current = chars[index]
        nxt = chars[index + 1] if index + 1 < len(chars) else ""

        if state == "code" and current == "/" and nxt == "/":
            chars[index] = chars[index + 1] = " "
            index += 2
            state = "line_comment"
            continue
        if state == "code" and current == "/" and nxt == "*":
            chars[index] = chars[index + 1] = " "
            index += 2
            state = "block_comment"
            continue
        if state == "code" and current == '"':
            chars[index] = " "
            index += 1
            state = "string"
            continue

        if state == "line_comment":
            if current == "\n":
                state = "code"
            else:
                chars[index] = " "
            index += 1
            continue

        if state == "block_comment":
            if current == "*" and nxt == "/":
                chars[index] = chars[index + 1] = " "
                index += 2
                state = "code"
            else:
                if current != "\n":
                    chars[index] = " "
                index += 1
            continue

        if state == "string":
            if current == "\\":
                chars[index] = " "
                if index + 1 < len(chars) and chars[index + 1] != "\n":
                    chars[index + 1] = " "
                    index += 2
                else:
                    index += 1
                continue
            if current == '"':
                chars[index] = " "
                state = "code"
            elif current != "\n":
                chars[index] = " "
            index += 1
            continue

        index += 1
    return "".join(chars)


def _module_ranges(text: str) -> list[tuple[re.Match, int]]:
    ranges = []
    for match in re.finditer(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)\b", text):
        end_match = re.search(r"\bendmodule\b", text[match.end() :])
        end = match.end() + end_match.end() if end_match else len(text)
        ranges.append((match, end))
    return ranges


def _header_end(text: str, start: int) -> int:
    semicolon = text.find(";", start)
    return semicolon if semicolon != -1 else len(text)


def _split_port_declarations(header: str) -> list[str]:
    return [part.strip() for part in header.replace("\n", " ").split(",") if part.strip()]


def _port_nodes(tree: SyntaxTree, module_match: re.Match) -> list[SyntaxNode]:
    header = tree.sanitized[module_match.end() : _header_end(tree.sanitized, module_match.end())]
    nodes = []
    for declaration in _split_port_declarations(header):
        if not re.search(r"\b(input|inout|output)\b", declaration):
            continue
        identifiers = IDENT_RE.findall(declaration)
        if not identifiers:
            continue
        name = identifiers[-1]
        offset = tree.sanitized.find(name, module_match.end())
        line, column = tree.line_column(offset)
        direction = "unknown"
        for keyword in ["input", "inout", "output"]:
            if keyword in identifiers:
                direction = keyword
                break
        nodes.append(
            SyntaxNode(
                kind="PortDeclaration",
                text=declaration,
                line=line,
                column=column,
                attrs={"name": name, "direction": direction},
            )
        )
    return nodes


def _always_nodes(tree: SyntaxTree, start: int, end: int) -> list[SyntaxNode]:
    nodes = []
    for match in re.finditer(r"\balways(?:_(ff|comb|latch))?\b", tree.sanitized[start:end]):
        suffix = match.group(1)
        absolute = start + match.start()
        line, column = tree.line_column(absolute)
        nodes.append(
            SyntaxNode(
                kind="AlwaysConstruct",
                text=match.group(0),
                line=line,
                column=column,
                attrs={"variant": suffix or "bare"},
            )
        )
    return nodes


def _instantiation_nodes(tree: SyntaxTree, known_modules: set[str], start: int, end: int) -> list[SyntaxNode]:
    nodes = []
    text = tree.sanitized[start:end]
    for match in IDENT_RE.finditer(text):
        module_type = match.group(0)
        if module_type not in known_modules:
            continue
        tail = text[match.end() :]
        index = 0
        while index < len(tail) and tail[index].isspace():
            index += 1
        if index < len(tail) and tail[index] == "#":
            index += 1
            while index < len(tail) and tail[index].isspace():
                index += 1
            if index >= len(tail) or tail[index] != "(":
                continue
            depth = 0
            while index < len(tail):
                if tail[index] == "(":
                    depth += 1
                elif tail[index] == ")":
                    depth -= 1
                    if depth == 0:
                        index += 1
                        break
                index += 1
        while index < len(tail) and tail[index].isspace():
            index += 1
        instance = IDENT_RE.match(tail, index)
        if not instance or instance.group(0) in known_modules:
            continue
        index = instance.end()
        while index < len(tail) and tail[index].isspace():
            index += 1
        if index >= len(tail) or tail[index] != "(":
            continue
        absolute = start + match.start()
        line, column = tree.line_column(absolute)
        nodes.append(
            SyntaxNode(
                kind="ModuleInstantiation",
                text=module_type,
                line=line,
                column=column,
                attrs={"module": module_type, "instance": instance.group(0)},
            )
        )
    return nodes


def parse_syntax_text(
    file: Path,
    text: str,
    verible_json: dict | None = None,
    known_modules: set[str] | None = None,
) -> SyntaxTree:
    sanitized = strip_comments_and_strings(text)
    placeholder = SyntaxTree(
        file=file,
        source=text,
        sanitized=sanitized,
        root=SyntaxNode(kind="Root", text=""),
        verible_json=verible_json,
    )
    module_matches = _module_ranges(sanitized)
    module_names = {match.group(1) for match, _end in module_matches}
    known_module_names = known_modules or module_names
    module_nodes = []
    for match, end in module_matches:
        line, column = placeholder.line_column(match.start(1))
        children = [
            *_port_nodes(placeholder, match),
            *_always_nodes(placeholder, match.end(), end),
            *_instantiation_nodes(placeholder, known_module_names, match.end(), end),
        ]
        module_nodes.append(
            SyntaxNode(
                kind="ModuleDeclaration",
                text=match.group(0),
                line=line,
                column=column,
                attrs={"name": match.group(1), "header_end": _header_end(sanitized, match.end())},
                children=tuple(children),
            )
        )

    return SyntaxTree(
        file=file,
        source=text,
        sanitized=sanitized,
        root=SyntaxNode(kind="Root", text="", children=tuple(module_nodes)),
        verible_json=verible_json,
    )


def parse_syntax_file(file: Path, prefer_verible: bool = True) -> SyntaxTree:
    verible_json = None
    if prefer_verible and shutil.which("verible-verilog-syntax") is not None:
        try:
            result = subprocess.run(
                ["verible-verilog-syntax", "--export_json", str(file)],
                timeout=10,
                text=True,
                capture_output=True,
            )
            if result.returncode == 0:
                import json

                verible_json = json.loads(result.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            verible_json = None
    return parse_syntax_text(file, file.read_text(), verible_json)
