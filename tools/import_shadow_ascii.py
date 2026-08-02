import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.render_shadow_map import parse_tile_set


ROW_RE = re.compile(r"^\s*(-?\d+)\s(.*)$")


def get_current_bounds(data):
    grid = data.get("normalized_grid") or {}
    points = set(parse_tile_set(grid.get("walkable_tiles")))
    points |= set(parse_tile_set(grid.get("inferred_blocker_tiles")))
    points |= set(parse_tile_set(grid.get("door_tiles")))
    if not points:
        width = int(grid.get("width") or 0)
        height = int(grid.get("height") or 0)
        return 0, max(0, width - 1), 0, max(0, height - 1)
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    return min_x, max_x, min_y, max_y


def extract_ascii_rows(text, default_min_y):
    lines = text.splitlines()
    header_seen = False
    started_rows = False
    expected_y = default_min_y
    rows = []
    for line in lines:
        if line.startswith("Legend:"):
            break
        if not header_seen:
            if line.startswith("    "):
                header_seen = True
            continue
        if not started_rows and not line.strip():
            rows.append((expected_y, ""))
            expected_y += 1
            started_rows = True
            continue
        match = ROW_RE.match(line)
        if match:
            started_rows = True
            y = int(match.group(1))
            row = match.group(2)
            rows.append((y, row))
            expected_y = y + 1
            continue
        if started_rows:
            rows.append((expected_y, line))
            expected_y += 1
    return rows


def import_ascii_into_json(txt_path: Path, json_path: Path):
    data = json.loads(json_path.read_text(encoding="utf-8"))
    min_x, max_x, min_y, max_y = get_current_bounds(data)
    rows = extract_ascii_rows(txt_path.read_text(encoding="utf-8"), min_y)

    walkable = set()
    blockers = set()
    doors = set()
    for y, row_text in rows:
        for idx, char in enumerate(row_text):
            x = min_x + idx
            if char == ".":
                walkable.add((x, y))
            elif char == "#":
                blockers.add((x, y))
            elif char == "D":
                doors.add((x, y))

    def fmt(coords):
        return sorted(f"{x},{y}" for x, y in coords)

    data["manual_overrides"] = {
        "mode": "replace_final_tiles",
        "source": "ascii_import",
        "source_file": str(txt_path),
        "walkable_tiles": fmt(walkable),
        "blocker_tiles": fmt(blockers),
        "door_tiles": fmt(doors),
    }

    from tools.shadow_mapper import build_normalized_grid

    data["normalized_grid"] = build_normalized_grid(data)
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {
        "walkable": len(walkable),
        "blockers": len(blockers),
        "doors": len(doors),
    }


def main():
    parser = argparse.ArgumentParser(description="Import manually corrected ASCII shadow maps back into JSON overrides.")
    parser.add_argument("txt_files", nargs="+", help="ASCII shadow-map .txt files to import.")
    args = parser.parse_args()

    for txt_name in args.txt_files:
        txt_path = Path(txt_name)
        if not txt_path.exists():
            raise SystemExit(f"File not found: {txt_path}")
        json_path = txt_path.with_suffix(".json")
        if not json_path.exists():
            raise SystemExit(f"Matching JSON not found for {txt_path}")
        stats = import_ascii_into_json(txt_path, json_path)
        print(
            f"Imported {txt_path.name} -> {json_path.name} "
            f"(walkable={stats['walkable']}, blockers={stats['blockers']}, doors={stats['doors']})"
        )


if __name__ == "__main__":
    main()
