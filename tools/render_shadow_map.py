import argparse
import json
from pathlib import Path


def parse_tile_set(values):
    coords = set()
    for value in values or []:
        try:
            x_str, y_str = str(value).split(",", 1)
            coords.add((int(x_str), int(y_str)))
        except Exception:
            continue
    return coords


def render_ascii(data, include_axes=True):
    grid = data.get("normalized_grid", {}) or {}
    walkable = parse_tile_set(grid.get("walkable_tiles"))
    blockers = parse_tile_set(grid.get("inferred_blocker_tiles"))
    door_tiles = parse_tile_set(grid.get("door_tiles"))

    points = set(walkable) | set(blockers) | set(door_tiles)
    if not points:
        return "(no normalized grid data)"

    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)

    rows = []
    if include_axes:
        header = "    " + "".join(f"{x % 10}" for x in range(min_x, max_x + 1))
        rows.append(header)

    for y in range(min_y, max_y + 1):
        chars = []
        for x in range(min_x, max_x + 1):
            if (x, y) in door_tiles:
                chars.append("D")
            elif (x, y) in walkable:
                chars.append(".")
            elif (x, y) in blockers:
                chars.append("#")
            else:
                chars.append(" ")
        line = "".join(chars)
        if include_axes:
            rows.append(f"{y:>3} {line}")
        else:
            rows.append(line)
    return "\n".join(rows)


def summarize(data):
    grid = data.get("normalized_grid", {}) or {}
    return {
        "label": data.get("label"),
        "map_id": data.get("map_id"),
        "map_name": data.get("map_name"),
        "width": grid.get("width"),
        "height": grid.get("height"),
        "walkable_tiles": len(grid.get("walkable_tiles", []) or []),
        "inferred_blocker_tiles": len(grid.get("inferred_blocker_tiles", []) or []),
        "door_tiles": len(grid.get("door_tiles", []) or []),
    }


def main():
    parser = argparse.ArgumentParser(description="Render a normalized shadow-map JSON as ASCII.")
    parser.add_argument("json_file", help="Path to a shadow map JSON file.")
    parser.add_argument("--output", help="Optional text file to write the ASCII render to.")
    parser.add_argument("--no-axes", action="store_true", help="Do not print coordinate axes.")
    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.exists():
        raise SystemExit(f"File not found: {json_path}")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    summary = summarize(data)
    ascii_map = render_ascii(data, include_axes=not args.no_axes)

    output_lines = [
        f"label: {summary['label']}",
        f"map: {summary['map_name']} ({summary['map_id']})",
        f"size: {summary['width']} x {summary['height']}",
        f"walkable: {summary['walkable_tiles']}",
        f"inferred blockers: {summary['inferred_blocker_tiles']}",
        f"door tiles: {summary['door_tiles']}",
        "",
        ascii_map,
        "",
        "Legend: .=walkable  #=inferred blocker  D=door/manual opening",
    ]
    output_text = "\n".join(output_lines)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"Saved ASCII render to: {out_path}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
