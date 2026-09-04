from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rtlflow.checks import strip_comments_and_strings


MODULE_RE = re.compile(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)\b", re.S)
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")


@dataclass(frozen=True)
class AdoptedConfig:
    name: str
    top: str
    sources: list[Path]
    testbench: str | None
    include_dirs: list[Path]
    top_candidates: list[str]
    ambiguous: bool


def find_source_files(path: Path) -> tuple[list[Path], Path | None]:
    if path.is_file():
        return [path], None
    file_lists = sorted(path.glob("*.f"))
    if file_lists:
        file_list = file_lists[0]
        sources = []
        for line in file_list.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            source = Path(line)
            if source.is_absolute():
                sources.append(source)
                continue
            file_list_relative = file_list.parent / source
            cwd_relative = Path.cwd() / source
            sources.append(file_list_relative if file_list_relative.exists() else cwd_relative)
        return sources, file_list
    return sorted([*path.rglob("*.sv"), *path.rglob("*.v")]), None


def module_names(text: str) -> list[str]:
    return [match.group(1) for match in MODULE_RE.finditer(strip_comments_and_strings(text))]


def instantiated_modules(text: str, known_modules: set[str]) -> set[str]:
    sanitized = strip_comments_and_strings(text)
    found = set()
    for match in IDENT_RE.finditer(sanitized):
        module_type = match.group(0)
        if module_type not in known_modules:
            continue
        tail = sanitized[match.end() :]
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
        if index < len(tail) and tail[index] == "(":
            found.add(module_type)
    return found


def module_has_no_ports(text: str, module_name: str) -> bool:
    sanitized = strip_comments_and_strings(text)
    match = re.search(rf"\bmodule\s+{re.escape(module_name)}\b", sanitized)
    if not match:
        return False
    semicolon = sanitized.find(";", match.end())
    if semicolon == -1:
        return False
    declaration_tail = sanitized[match.end() : semicolon].strip()
    if declaration_tail.startswith("#"):
        close = declaration_tail.rfind(")")
        declaration_tail = declaration_tail[close + 1 :].strip() if close != -1 else declaration_tail
    if not declaration_tail:
        return True
    if declaration_tail.startswith("("):
        return not declaration_tail.strip("() \t\r\n")
    return False


def infer_adoption(path: Path) -> AdoptedConfig:
    path = path.resolve()
    sources, file_list = find_source_files(path)
    modules_by_file = {}
    for source in sources:
        modules_by_file[source] = module_names(source.read_text())

    known_modules = {
        module
        for modules in modules_by_file.values()
        for module in modules
    }
    instantiated = set()
    for source in sources:
        instantiated.update(instantiated_modules(source.read_text(), known_modules))

    testbench_candidates = []
    for source, modules in modules_by_file.items():
        text = source.read_text()
        source_instantiations = instantiated_modules(text, known_modules)
        for module in modules:
            if module_has_no_ports(text, module) and any(
                candidate != module for candidate in source_instantiations
            ):
                testbench_candidates.append(module)

    design_candidates = sorted((known_modules - set(testbench_candidates)) - instantiated)
    candidates = design_candidates or sorted(known_modules - instantiated) or sorted(known_modules)
    testbench = None
    if testbench_candidates:
        testbench = sorted(testbench_candidates)[0]
        candidates = sorted(instantiated) or candidates

    include_dirs = sorted({header.parent for header in path.rglob("*.svh")}) if path.is_dir() else []
    top = testbench or (candidates[0] if candidates else path.stem)
    name = top.replace("_tb", "")
    return AdoptedConfig(
        name=name,
        top=top,
        sources=sources,
        testbench=testbench,
        include_dirs=include_dirs,
        top_candidates=candidates,
        ambiguous=len(candidates) > 1 and testbench is None,
    )


def write_adopted_config(adopted: AdoptedConfig, output_path: Path, source_root: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"name: {adopted.name}",
        f"top: {adopted.top}",
        "sources: files.f",
        "parameters: {}",
        "timeout_sec: 60",
    ]
    if adopted.include_dirs:
        lines.append("include_dirs:")
        for include_dir in adopted.include_dirs:
            lines.append(f"  - {include_dir}")
    output_path.write_text("\n".join(lines) + "\n")

    file_list = output_path.parent / "files.f"
    file_list.write_text("\n".join(source.resolve().as_posix() for source in adopted.sources) + "\n")
    return output_path
