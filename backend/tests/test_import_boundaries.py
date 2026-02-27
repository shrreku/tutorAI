import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
RUNTIME_ROOT = APP_ROOT / "services" / "tutor_runtime"
INGESTION_ROOT = APP_ROOT / "services" / "ingestion"


def _module_name(root: Path, path: Path, package_prefix: str) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = rel.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return package_prefix
    return f"{package_prefix}.{'.'.join(parts)}"


def _iter_modules(root: Path, package_prefix: str) -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for path in root.rglob("*.py"):
        modules[_module_name(root, path, package_prefix)] = path
    return modules


def _resolve_from_import(current_module: str, node: ast.ImportFrom) -> set[str]:
    if node.level == 0:
        return {node.module} if node.module else set()

    package_parts = current_module.split(".")[:-1]
    up_levels = node.level - 1
    if up_levels > len(package_parts):
        return set()

    base_parts = package_parts[: len(package_parts) - up_levels]
    if node.module:
        base_parts.extend(node.module.split("."))
        return {".".join(base_parts)}

    return {".".join(base_parts + [alias.name]) for alias in node.names}


def _module_imports(root: Path, package_prefix: str) -> dict[str, set[str]]:
    modules = _iter_modules(root, package_prefix)
    imports_by_module: dict[str, set[str]] = {module: set() for module in modules}

    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.update(_resolve_from_import(module, node))

        imports_by_module[module] = {imported for imported in imports if imported}

    return imports_by_module


def _import_graph(root: Path, package_prefix: str) -> dict[str, set[str]]:
    imports_by_module = _module_imports(root, package_prefix)
    module_names = set(imports_by_module)

    return {
        module: {imp for imp in imports if imp in module_names}
        for module, imports in imports_by_module.items()
    }


def _find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    visited: set[str] = set()
    active: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        visited.add(node)
        active.add(node)
        stack.append(node)

        for neighbor in sorted(graph[node]):
            if neighbor not in visited:
                found = dfs(neighbor)
                if found:
                    return found
            elif neighbor in active:
                start = stack.index(neighbor)
                return stack[start:] + [neighbor]

        stack.pop()
        active.remove(node)
        return None

    for node in sorted(graph):
        if node not in visited:
            found = dfs(node)
            if found:
                return found

    return None


def test_tutor_runtime_has_no_import_cycles():
    graph = _import_graph(RUNTIME_ROOT, "app.services.tutor_runtime")
    cycle = _find_cycle(graph)
    assert cycle is None, f"runtime import cycle detected: {' -> '.join(cycle)}"


def test_runtime_ingestion_boundaries_are_clean():
    runtime_imports = _module_imports(RUNTIME_ROOT, "app.services.tutor_runtime")
    ingestion_imports = _module_imports(INGESTION_ROOT, "app.services.ingestion")

    for module, imports in runtime_imports.items():
        bad = sorted(i for i in imports if i.startswith("app.services.ingestion"))
        assert not bad, f"{module} must not import ingestion modules: {bad}"
        assert (
            "app.services.tutor.turn_pipeline" not in imports
        ), f"{module} must not import legacy turn_pipeline shim"

    for module, imports in ingestion_imports.items():
        bad = sorted(i for i in imports if i.startswith("app.services.tutor_runtime"))
        assert not bad, f"{module} must not import tutor_runtime modules: {bad}"
