from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rtlflow.syntax import parse_syntax_file, parse_syntax_text


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
    tree = parse_syntax_text(Path("<memory>"), text)
    return [module.attrs["name"] for module in tree.find_all("ModuleDeclaration")]


def instantiated_modules(text: str, known_modules: set[str]) -> set[str]:
    tree = parse_syntax_text(Path("<memory>"), text, known_modules=known_modules)
    return {
        instance.attrs["module"]
        for instance in tree.find_all("ModuleInstantiation")
        if instance.attrs["module"] in known_modules
    }


def module_has_no_ports(text: str, module_name: str) -> bool:
    tree = parse_syntax_text(Path("<memory>"), text)
    for module in tree.find_all("ModuleDeclaration"):
        if module.attrs["name"] != module_name:
            continue
        return not tree.find_children(module, "PortDeclaration")
    return False


def infer_adoption(path: Path) -> AdoptedConfig:
    path = path.resolve()
    sources, file_list = find_source_files(path)
    first_pass_trees = {source: parse_syntax_file(source) for source in sources}

    known_modules = {
        module.attrs["name"]
        for tree in first_pass_trees.values()
        for module in tree.find_all("ModuleDeclaration")
    }
    trees_by_file = {
        source: parse_syntax_text(source, source.read_text(), known_modules=known_modules)
        for source in sources
    }
    instantiated = {
        instance.attrs["module"]
        for tree in trees_by_file.values()
        for instance in tree.find_all("ModuleInstantiation")
        if instance.attrs["module"] in known_modules
    }

    testbench_candidates = []
    for tree in trees_by_file.values():
        for module in tree.find_all("ModuleDeclaration"):
            module_name = module.attrs["name"]
            source_instantiations = {
                instance.attrs["module"]
                for instance in tree.find_children(module, "ModuleInstantiation")
                if instance.attrs["module"] in known_modules
            }
            if not tree.find_children(module, "PortDeclaration") and any(
                candidate != module_name for candidate in source_instantiations
            ):
                testbench_candidates.append(module_name)

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
