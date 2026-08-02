#!/usr/bin/env python3
"""Import an offline dungeon-curation CSV into per-dungeon annotations.json."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


COORDINATE_RE = re.compile(r"^[A-Z]+[1-9][0-9]*$")
VALID_TRAVERSAL = {
    "blocked",
    "conditional",
    "confirmed_walkable",
    "unverified",
    "unknown",
}
FIELDS = {
    "dungeon",
    "coordinate",
    "traversal",
    "object",
    "required_action",
    "notes",
}


def normalized_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = FIELDS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")
        rows = []
        current_dungeon = ""
        for line_number, raw in enumerate(reader, start=2):
            row = {key: (raw.get(key) or "").strip() for key in FIELDS}
            if not any(row.values()):
                continue
            if row["dungeon"]:
                current_dungeon = row["dungeon"]
            else:
                row["dungeon"] = current_dungeon
            row["coordinate"] = row["coordinate"].upper()
            if not row["dungeon"]:
                raise ValueError(
                    f"Line {line_number}: dungeon is required before continuation rows"
                )
            if not COORDINATE_RE.fullmatch(row["coordinate"]):
                raise ValueError(
                    f"Line {line_number}: invalid coordinate {row['coordinate']!r}"
                )
            if row["traversal"] not in VALID_TRAVERSAL:
                raise ValueError(
                    f"Line {line_number}: invalid traversal "
                    f"{row['traversal']!r}; expected one of "
                    f"{', '.join(sorted(VALID_TRAVERSAL))}"
                )
            rows.append(row)
    return rows


def import_rows(root: Path, rows: list[dict[str, str]], dry_run: bool = False):
    known_dungeons = {
        folder.name: folder
        for folder in root.iterdir()
        if folder.is_dir()
    }
    changed = {}
    for row in rows:
        folder = known_dungeons.get(row["dungeon"])
        if folder is None:
            raise ValueError(f"Unknown dungeon: {row['dungeon']!r}")
        annotation_path = folder / "annotations.json"
        payload = changed.get(annotation_path)
        if payload is None:
            payload = (
                json.loads(annotation_path.read_text(encoding="utf-8"))
                if annotation_path.exists()
                else {
                    "schema": "lufia2-dungeon-annotations-v2",
                    "dungeon": row["dungeon"],
                    "annotations": {},
                }
            )
        payload["schema"] = "lufia2-dungeon-annotations-v2"
        annotations = payload.setdefault("annotations", {})
        annotation = {
            "traversal": row["traversal"],
            "object": row["object"] or None,
            "required_action": row["required_action"] or None,
            "notes": row["notes"] or None,
        }
        annotations[row["coordinate"]] = annotation
        changed[annotation_path] = payload

    if not dry_run:
        for path, payload in changed.items():
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    return {
        "rows": len(rows),
        "dungeons": len({row["dungeon"] for row in rows}),
        "files": len(changed),
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import dungeon object/wall/passability annotations from CSV."
    )
    parser.add_argument("csv_file")
    parser.add_argument("--root", default="emulator/maps/Dungeons")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = normalized_rows(Path(args.csv_file))
    result = import_rows(Path(args.root), rows, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False))
    if not args.dry_run:
        print(
            "Annotations imported. Re-run "
            "python tools\\build_all_dungeon_navigation_maps.py "
            "to refresh generated maps."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
