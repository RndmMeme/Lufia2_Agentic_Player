#!/usr/bin/env python3
"""Fail fast when the active Mesen workspace regains legacy dependencies."""

from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ACTIVE_CODE = (ROOT / "agent", ROOT / "emulator", ROOT / "tools", ROOT / "wram_discovery")
BANNED_IMPORT_ROOTS = {
    "stable_baselines3",
    "torch",
    "chromadb",
    "pydirectinput",
    "pygetwindow",
}


def python_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    return imports


def audit() -> dict:
    errors = []
    checked_python = 0
    for root in ACTIVE_CODE:
        for path in root.rglob("*.py"):
            checked_python += 1
            banned = sorted(python_imports(path) & BANNED_IMPORT_ROOTS)
            if banned:
                errors.append(f"{path.relative_to(ROOT)} imports legacy dependencies: {banned}")

    manifest_path = ROOT / "data/runtime_knowledge_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    knowledge_paths = []
    for group in ("state_truth", "retrieval_sources", "structured_runtime", "visual_runtime"):
        for relative in manifest.get(group, []):
            knowledge_paths.append(relative)
            if not (ROOT / relative).exists():
                errors.append(f"Missing knowledge path: {relative}")

    dungeon_root = ROOT / "emulator/maps/Dungeons"
    dungeons = [path for path in dungeon_root.iterdir() if path.is_dir()]
    compiled = [path for path in dungeons if (path / "navigation/compiled_curation.json").exists()]
    if len(compiled) != len(dungeons):
        missing = sorted(path.name for path in dungeons if path not in compiled)
        errors.append(f"Dungeons without compiled curation: {missing}")

    return {
        "ok": not errors,
        "errors": errors,
        "python_files_checked": checked_python,
        "knowledge_paths_checked": len(knowledge_paths),
        "dungeons": len(dungeons),
        "compiled_dungeons": len(compiled),
    }


def main() -> int:
    report = audit()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
