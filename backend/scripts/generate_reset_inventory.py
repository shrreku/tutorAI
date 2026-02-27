#!/usr/bin/env python3
"""Generate cleanup-first architecture reset inventory report.

Usage:
    python3 backend/scripts/generate_reset_inventory.py
"""

from __future__ import annotations

import ast
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"
OUTPUT_PATH = REPO_ROOT / "docs" / "RESET-00-CODEBASE-INVENTORY.md"

LEGACY_PATTERNS = [
    r"\bcurriculum_phase_index\b",
    r"\bphase_skeleton\b",
    r"\bObjectivePhase\b",
    r"\bINTERMEDIATE_STEP\b",
    r"\bintermediate_step\b",
    r"\bintermediate_step_count\b",
    r"\bMAX_INTERMEDIATE_STEPS\b",
    r"\blegacy_path_used\b",
]

MIGRATE_SPLIT = {
    "services/ingestion/enricher.py",
    "services/ingestion/pipeline.py",
    "services/ingestion/ontology_extractor.py",
    "services/ingestion/graph_builder.py",
    "services/ingestion/kb_builder.py",
}

MIGRATE_CONSOLIDATE = {
    "api/v1/sessions.py",
    "services/tutor/session_service.py",
}

MIGRATE_PRUNE = {
    "services/llm/openai_provider.py",
}

REMOVE_CANDIDATES: set[str] = set()


@dataclass
class ModuleInfo:
    module: str
    rel_path: str
    abs_path: Path
    size_bytes: int
    imports: set[str]
    imported_by: set[str]
    legacy_hits: Counter


def _iter_py_files() -> Iterable[Path]:
    for path in APP_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def _module_name(path: Path) -> str:
    rel = path.relative_to(APP_ROOT).as_posix()
    return "app." + rel[:-3].replace("/", ".")


def _owner_for_path(rel_path: str) -> str:
    if rel_path.startswith("api/"):
        return "backend-api"
    if rel_path.startswith("agents/"):
        return "agent-runtime"
    if rel_path.startswith("services/tutor"):
        return "tutor-runtime"
    if rel_path.startswith("services/ingestion"):
        return "ingestion-core"
    if rel_path.startswith("services/retrieval"):
        return "retrieval-core"
    if rel_path.startswith("services/llm"):
        return "platform-llm"
    if rel_path.startswith("services/embedding"):
        return "platform-embeddings"
    if rel_path.startswith("services/neo4j"):
        return "platform-graph"
    if rel_path.startswith("services/"):
        return "platform-core"
    if rel_path.startswith("schemas/"):
        return "data-contracts"
    if rel_path.startswith("models/"):
        return "data-model"
    if rel_path.startswith("db/"):
        return "data-access"
    return "backend-core"


def _classify(rel_path: str, legacy_hits: Counter) -> tuple[str, str]:
    if rel_path in REMOVE_CANDIDATES:
        return (
            "REMOVE_CANDIDATE",
            "Temporary compatibility adapter slated for deletion after v3 cutover.",
        )
    if rel_path in MIGRATE_SPLIT:
        return (
            "MIGRATE_SPLIT",
            "Oversized/high-coupling module; split into stage-focused modules.",
        )
    if rel_path in MIGRATE_CONSOLIDATE:
        return (
            "MIGRATE_CONSOLIDATE",
            "Contains overlapping session lifecycle responsibilities; consolidate to one boundary.",
        )
    if rel_path in MIGRATE_PRUNE:
        return (
            "MIGRATE_PRUNE",
            "Keep provider boundary but remove legacy coercion/deprecated normalization paths.",
        )
    if legacy_hits:
        return (
            "MIGRATE_LEGACY",
            "Contains legacy-era symbols requiring targeted cleanup in reset tracks.",
        )
    return ("KEEP", "No immediate reset action required beyond routine refactoring.")


def _extract_imports(module_name: str, path: Path) -> set[str]:
    imports: set[str] = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app."):
                    imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            if node.level == 0:
                target = node.module
            else:
                parts = module_name.split(".")[:-1]
                if node.level > len(parts):
                    target = node.module
                else:
                    prefix = parts[: len(parts) - node.level + 1]
                    target = ".".join(prefix + ([node.module] if node.module else []))
            if target.startswith("app."):
                imports.add(target)

    return imports


def _legacy_hits(path: Path) -> Counter:
    text = path.read_text(encoding="utf-8")
    hits = Counter()
    for pat in LEGACY_PATTERNS:
        matches = re.findall(pat, text)
        if matches:
            hits[pat.strip("\\b")] = len(matches)
    return hits


def _duplicate_helper_names(paths: list[Path]) -> dict[str, list[str]]:
    seen: defaultdict[str, list[str]] = defaultdict(list)
    for path in paths:
        rel = path.relative_to(APP_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                seen[node.name].append(rel)

    duplicates: dict[str, list[str]] = {}
    for name, files in seen.items():
        unique = sorted(set(files))
        if len(unique) < 2:
            continue
        if name.startswith("_extract_") or name.startswith("_build_") or name in {
            "create_session",
            "get_session",
            "end_session",
        }:
            duplicates[name] = unique
    return dict(sorted(duplicates.items()))


def _markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    sep = ["---"] * len(header)
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join(sep) + " |"]
    for row in rows[1:]:
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


def generate() -> None:
    paths = sorted(_iter_py_files())
    modules = {_module_name(p): p for p in paths}

    imports_map: dict[str, set[str]] = {}
    reverse_map: defaultdict[str, set[str]] = defaultdict(set)

    for module_name, path in modules.items():
        imports = _extract_imports(module_name, path)
        imports_map[module_name] = imports

    for src, targets in imports_map.items():
        for target in targets:
            if target in modules:
                reverse_map[target].add(src)
            elif target + ".__init__" in modules:
                reverse_map[target + ".__init__"].add(src)

    module_infos: list[ModuleInfo] = []
    for module_name, path in modules.items():
        rel = path.relative_to(APP_ROOT).as_posix()
        module_infos.append(
            ModuleInfo(
                module=module_name,
                rel_path=rel,
                abs_path=path,
                size_bytes=path.stat().st_size,
                imports=imports_map.get(module_name, set()),
                imported_by=reverse_map.get(module_name, set()),
                legacy_hits=_legacy_hits(path),
            )
        )

    duplicates = _duplicate_helper_names(paths)

    class_counts = Counter()
    classified: list[tuple[ModuleInfo, str, str, str]] = []
    for info in module_infos:
        cls, rationale = _classify(info.rel_path, info.legacy_hits)
        owner = _owner_for_path(info.rel_path)
        class_counts[cls] += 1
        classified.append((info, cls, owner, rationale))

    classified.sort(key=lambda t: (t[1], -t[0].size_bytes, t[0].rel_path))
    top30 = sorted(module_infos, key=lambda m: m.size_bytes, reverse=True)[:30]

    legacy_rows = []
    for info in sorted(module_infos, key=lambda m: (-sum(m.legacy_hits.values()), m.rel_path)):
        if not info.legacy_hits:
            continue
        summary = ", ".join(f"{k}:{v}" for k, v in sorted(info.legacy_hits.items()))
        legacy_rows.append([info.rel_path, str(sum(info.legacy_hits.values())), summary])

    immediate_delete = [item for item in classified if item[1] == "REMOVE_CANDIDATE"]
    migration_candidates = [item for item in classified if item[1].startswith("MIGRATE")]

    lines: list[str] = []
    lines.append("# RESET-00 Codebase Inventory")
    lines.append("")
    lines.append("Generated by `backend/scripts/generate_reset_inventory.py`.")
    lines.append("")
    lines.append(f"- Generated at (UTC): {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Scope: `{APP_ROOT.relative_to(REPO_ROOT).as_posix()}`")
    lines.append(f"- Total Python modules scanned: {len(module_infos)}")
    lines.append("")
    lines.append("## Classification Summary")
    lines.append("")
    summary_rows = [["Classification", "Count"]]
    for cls in sorted(class_counts):
        summary_rows.append([cls, str(class_counts[cls])])
    lines.append(_markdown_table(summary_rows))
    lines.append("")

    lines.append("## Top 30 Largest Modules")
    lines.append("")
    top_rows = [["Module", "Size (bytes)"]]
    for info in top30:
        top_rows.append([info.rel_path, str(info.size_bytes)])
    lines.append(_markdown_table(top_rows))
    lines.append("")

    lines.append("## Duplicate Helper Functions")
    lines.append("")
    if duplicates:
        dup_rows = [["Function", "Files"]]
        for name, files in duplicates.items():
            dup_rows.append([name, "<br>".join(files)])
        lines.append(_markdown_table(dup_rows))
    else:
        lines.append("No duplicate helper-function patterns detected.")
    lines.append("")

    lines.append("## Legacy Symbol Hits")
    lines.append("")
    if legacy_rows:
        lines.append(_markdown_table([["File", "Total Hits", "Hit Detail"], *legacy_rows]))
    else:
        lines.append("No legacy symbol hits detected for configured pattern set.")
    lines.append("")

    lines.append("## Immediate Delete Candidates")
    lines.append("")
    if immediate_delete:
        del_rows = [["Module", "Owner", "Reason"]]
        for info, _, owner, rationale in immediate_delete:
            del_rows.append([info.rel_path, owner, rationale])
        lines.append(_markdown_table(del_rows))
    else:
        lines.append("None identified in this pass.")
    lines.append("")

    lines.append("## Migration Candidates")
    lines.append("")
    mig_rows = [["Module", "Class", "Owner", "Reason"]]
    for info, cls, owner, rationale in migration_candidates:
        mig_rows.append([info.rel_path, cls, owner, rationale])
    lines.append(_markdown_table(mig_rows if len(mig_rows) > 1 else [["Module", "Class", "Owner", "Reason"], ["None", "-", "-", "-"]]))
    lines.append("")

    lines.append("## Full Module Classification (Keep/Remove/Migrate)")
    lines.append("")
    full_rows = [[
        "Module",
        "Class",
        "Owner",
        "Size",
        "Imported By",
        "Imports",
        "Legacy Hits",
        "Rationale",
    ]]
    for info, cls, owner, rationale in classified:
        legacy_total = str(sum(info.legacy_hits.values())) if info.legacy_hits else "0"
        full_rows.append([
            info.rel_path,
            cls,
            owner,
            str(info.size_bytes),
            str(len(info.imported_by)),
            str(len(info.imports)),
            legacy_total,
            rationale,
        ])
    lines.append(_markdown_table(full_rows))
    lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    generate()
