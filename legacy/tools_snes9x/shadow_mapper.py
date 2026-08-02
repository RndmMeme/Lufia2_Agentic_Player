import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.runtime_config import get_helper_executable_path, get_helper_startup_delay
from emulator.memory_reader import MemoryReader


BLOCKING_TO_DIRECTION = {
    0: "north",
    1: "south",
    2: "west",
    3: "east",
}


def sanitize_name(text):
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(text or "unknown"))
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe.strip("_") or "unknown"


def canonical_pos(state):
    dx = state.get("dungeon_x")
    dy = state.get("dungeon_y")
    if dx is None or dy is None:
        dx = state.get("x", 0)
        dy = state.get("y", 0)
    return int(dx or 0), int(dy or 0)


def build_output_path(output_dir: Path, state, label):
    map_id = int(state.get("map_id", 0) or 0)
    map_name = sanitize_name(state.get("map_name", f"map_{map_id:02X}"))
    suffix = sanitize_name(label) if label else f"map_{map_id:02X}_{map_name}"
    return output_dir / f"{suffix}.json"


def empty_record(label=None):
    return {
        "label": label or None,
        "map_id": None,
        "map_name": None,
        "coord_mode": "logical_step_grid",
        "visited_tiles": {},
        "blocked_edges": {},
        "path": [],
        "normalized_grid": {},
        "bounds": {
            "min_x": None,
            "max_x": None,
            "min_y": None,
            "max_y": None,
        },
        "sessions": [],
        "updated_at": None,
    }


def load_record(path: Path, label=None):
    if not path.exists():
        return empty_record(label=label)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = empty_record(label=label)
    if not isinstance(data, dict):
        data = empty_record(label=label)
    data.setdefault("label", label or data.get("label"))
    data.setdefault("visited_tiles", {})
    data.setdefault("blocked_edges", {})
    data.setdefault("path", [])
    data.setdefault("normalized_grid", {})
    data.setdefault("manual_overrides", {})
    data.setdefault("sessions", [])
    data.setdefault("bounds", {"min_x": None, "max_x": None, "min_y": None, "max_y": None})
    return data


def update_bounds(bounds, x, y):
    for key, value in (("min_x", x), ("max_x", x), ("min_y", y), ("max_y", y)):
        current = bounds.get(key)
        if current is None:
            bounds[key] = value
        elif key.startswith("min"):
            bounds[key] = min(current, value)
        else:
            bounds[key] = max(current, value)


def record_step(data, x, y, now):
    tile_key = f"{x},{y}"
    tile = data["visited_tiles"].setdefault(tile_key, {
        "x": x,
        "y": y,
        "visits": 0,
        "first_seen": now,
        "last_seen": now,
    })
    tile["visits"] += 1
    tile["last_seen"] = now
    update_bounds(data["bounds"], x, y)


def record_blocked_edge(data, x, y, direction, now):
    if direction not in BLOCKING_TO_DIRECTION.values():
        return
    edge_key = f"{x},{y},{direction}"
    edge = data["blocked_edges"].setdefault(edge_key, {
        "x": x,
        "y": y,
        "direction": direction,
        "hits": 0,
        "first_seen": now,
        "last_seen": now,
    })
    edge["hits"] += 1
    edge["last_seen"] = now


def _continuous_unwrap_points(points):
    if not points:
        return []

    unwrapped = []
    prev_raw_x = prev_raw_y = None
    cur_x = cur_y = None
    for raw_x, raw_y in points:
        raw_x = int(raw_x)
        raw_y = int(raw_y)
        if cur_x is None:
            cur_x, cur_y = raw_x, raw_y
        else:
            dx = raw_x - prev_raw_x
            dy = raw_y - prev_raw_y
            if dx > 128:
                dx -= 256
            elif dx < -128:
                dx += 256
            if dy > 128:
                dy -= 256
            elif dy < -128:
                dy += 256
            cur_x += dx
            cur_y += dy
        unwrapped.append((cur_x, cur_y))
        prev_raw_x, prev_raw_y = raw_x, raw_y
    return unwrapped


def _should_flip_axis(unwrapped_points, axis_index, lookahead=40):
    if not unwrapped_points:
        return False
    start = unwrapped_points[0][axis_index]
    deltas = [
        point[axis_index] - start
        for point in unwrapped_points[1:lookahead]
        if point[axis_index] != start
    ]
    if not deltas:
        return False
    negatives = sum(1 for value in deltas if value < 0)
    positives = sum(1 for value in deltas if value > 0)
    return negatives > positives


def build_normalized_grid(data, seam_threshold=224, snap=16):
    raw_path = [
        (point.get("x"), point.get("y"))
        for point in (data.get("path") or [])
        if point.get("x") is not None and point.get("y") is not None
    ]
    raw_points = raw_path or [
        (value.get("x"), value.get("y"))
        for value in (data.get("visited_tiles") or {}).values()
        if value.get("x") is not None and value.get("y") is not None
    ]
    if not raw_points:
        return {}

    unwrapped = _continuous_unwrap_points(raw_points)
    flip_x = _should_flip_axis(unwrapped, 0)
    flip_y = _should_flip_axis(unwrapped, 1)
    oriented = [
        ((-x if flip_x else x), (-y if flip_y else y))
        for x, y in unwrapped
    ]
    snapped = [(int(round(x / snap) * snap), int(round(y / snap) * snap)) for x, y in oriented]

    x_axis = sorted({x for x, _ in snapped})
    y_axis = sorted({y for _, y in snapped})
    x_index = {x: idx for idx, x in enumerate(x_axis)}
    y_index = {y: idx for idx, y in enumerate(y_axis)}
    snapped_point_lookup = {}
    for raw_point, snapped_point in zip(raw_points, snapped):
        key = f"{int(raw_point[0])},{int(raw_point[1])}"
        snapped_point_lookup.setdefault(key, snapped_point)

    walkable_tiles = sorted({
        f"{x_index[x]},{y_index[y]}"
        for x, y in snapped
    }, key=lambda key: tuple(int(part) for part in key.split(",")))

    walkable_coords = {
        tuple(int(part) for part in key.split(","))
        for key in walkable_tiles
    }

    row_bounds = {}
    col_bounds = {}
    for gx, gy in walkable_coords:
        row = row_bounds.setdefault(gy, {"min_x": gx, "max_x": gx})
        row["min_x"] = min(row["min_x"], gx)
        row["max_x"] = max(row["max_x"], gx)
        col = col_bounds.setdefault(gx, {"min_y": gy, "max_y": gy})
        col["min_y"] = min(col["min_y"], gy)
        col["max_y"] = max(col["max_y"], gy)

    inferred_blockers = set()
    for gy, bounds in row_bounds.items():
        inferred_blockers.add((bounds["min_x"] - 1, gy))
        inferred_blockers.add((bounds["max_x"] + 1, gy))
    for gx, bounds in col_bounds.items():
        inferred_blockers.add((gx, bounds["min_y"] - 1))
        inferred_blockers.add((gx, bounds["max_y"] + 1))

    # Keep only blockers immediately outside the explored footprint and never on walkable cells.
    blocker_tiles = sorted(
        {
            f"{bx},{by}"
            for bx, by in inferred_blockers
            if (bx, by) not in walkable_coords
        },
        key=lambda key: tuple(int(part) for part in key.split(",")),
    )

    normalized_blocked_edges = []
    observed_blocked_neighbor_tiles = set()
    for edge in (data.get("blocked_edges") or {}).values():
        try:
            raw_x = int(edge.get("x"))
            raw_y = int(edge.get("y"))
        except Exception:
            continue
        direction = str(edge.get("direction") or "").lower()
        if direction not in BLOCKING_TO_DIRECTION.values():
            continue

        snapped_anchor = snapped_point_lookup.get(f"{raw_x},{raw_y}")
        if snapped_anchor is None:
            oriented_x = -raw_x if flip_x else raw_x
            oriented_y = -raw_y if flip_y else raw_y
            snapped_anchor = (
                int(round(oriented_x / snap) * snap),
                int(round(oriented_y / snap) * snap),
            )
        sx, sy = snapped_anchor
        if sx not in x_index or sy not in y_index:
            continue
        gx = x_index[sx]
        gy = y_index[sy]
        normalized_blocked_edges.append({
            "x": gx,
            "y": gy,
            "direction": direction,
            "hits": int(edge.get("hits", 0) or 0),
        })
        nx, ny = gx, gy
        if direction == "north":
            ny -= 1
        elif direction == "south":
            ny += 1
        elif direction == "west":
            nx -= 1
        elif direction == "east":
            nx += 1
        observed_blocked_neighbor_tiles.add((nx, ny))

    normalized = {
        "unwrap": {
            "seam_threshold": seam_threshold,
            "byte_wrap": 256,
            "method": "continuous_path_unwrap",
        },
        "snap": {
            "size": snap,
            "method": "nearest",
        },
        "orientation": {
            "flip_x": flip_x,
            "flip_y": flip_y,
        },
        "raw_axis_x": x_axis,
        "raw_axis_y": y_axis,
        "width": len(x_axis),
        "height": len(y_axis),
        "walkable_tiles": walkable_tiles,
        "inferred_blocker_tiles": blocker_tiles,
        "blocked_edges": sorted(
            normalized_blocked_edges,
            key=lambda edge: (edge["y"], edge["x"], edge["direction"]),
        ),
        "observed_blocked_neighbor_tiles": sorted(
            {f"{x},{y}" for x, y in observed_blocked_neighbor_tiles},
            key=lambda key: tuple(int(part) for part in key.split(",")),
        ),
        "inference_notes": [
            "Blockers are inferred from the furthest walked tile on each row and column.",
            "Doorways or special pass-through openings may need manual correction afterward.",
            "Blocked edges come from DungeonBlocking collision results and indicate an impassable step, not the blocker type.",
        ],
    }

    manual = data.get("manual_overrides") or {}
    if manual.get("mode") == "replace_final_tiles":
        walkable_tiles = sorted(manual.get("walkable_tiles") or [])
        blocker_tiles = sorted(manual.get("blocker_tiles") or [])
        door_tiles = sorted(manual.get("door_tiles") or [])
        if walkable_tiles or blocker_tiles or door_tiles:
            normalized["walkable_tiles"] = walkable_tiles
            normalized["inferred_blocker_tiles"] = blocker_tiles
            normalized["door_tiles"] = door_tiles
            x_values = []
            y_values = []
            for tile_value in walkable_tiles + blocker_tiles + door_tiles:
                try:
                    x_str, y_str = str(tile_value).split(",", 1)
                    x_values.append(int(x_str))
                    y_values.append(int(y_str))
                except Exception:
                    continue
            if x_values and y_values:
                normalized["manual_bounds"] = {
                    "min_x": min(x_values),
                    "max_x": max(x_values),
                    "min_y": min(y_values),
                    "max_y": max(y_values),
                }
            normalized.setdefault("inference_notes", []).append(
                "Final tile sets are being replaced by manual ASCII-imported overrides."
            )

    return normalized


def save_record(path: Path, data):
    data["normalized_grid"] = build_normalized_grid(data)
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def start_helper_if_needed():
    helper_path = get_helper_executable_path(PROJECT_ROOT)
    if not helper_path.exists():
        raise SystemExit(f"Helper not found: {helper_path}")
    process = subprocess.Popen(
        [str(helper_path)],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    time.sleep(max(1, int(get_helper_startup_delay())))
    return process


def main():
    parser = argparse.ArgumentParser(description="Shadow-map walked dungeon tiles into a persistent JSON file.")
    parser.add_argument("--output-dir", default="data/shadow_maps")
    parser.add_argument("--label", help="Optional logical room/segment label, e.g. secret_skills_cave_room_1")
    parser.add_argument("--map-id", type=int, help="If set, only record while on this map id.")
    parser.add_argument("--poll", type=float, default=0.10, help="Polling interval in seconds.")
    parser.add_argument("--save-every", type=float, default=1.0, help="Periodic save interval in seconds.")
    parser.add_argument("--path-limit", type=int, default=5000, help="Maximum number of path points to keep.")
    parser.add_argument("--launch-helper", action="store_true", help="Launch the C# helper if it is not already running.")
    args = parser.parse_args()

    reader = MemoryReader()
    helper_proc = start_helper_if_needed() if args.launch_helper else None
    output_dir = PROJECT_ROOT / args.output_dir

    last_saved = 0.0
    last_pos = None
    last_block_signature = None
    current_output = None
    data = None
    session_started = time.strftime("%Y-%m-%dT%H:%M:%S")

    print("=" * 72)
    print(" LUFIA 2 SHADOW MAPPER ")
    print("=" * 72)
    print("Walk manually. This tool records stepped tiles without wiping existing data.")
    print("Press Ctrl+C to stop.")
    print("-" * 72)

    try:
        while True:
            state = reader.get_game_state()
            if not state.get("_reader_ready"):
                time.sleep(args.poll)
                continue

            map_id = int(state.get("map_id", 0) or 0)
            if args.map_id is not None and map_id != args.map_id:
                time.sleep(args.poll)
                continue

            pos = canonical_pos(state)
            if pos == (0, 0):
                time.sleep(args.poll)
                continue

            output_path = build_output_path(output_dir, state, args.label)
            if current_output != output_path:
                current_output = output_path
                data = load_record(output_path, label=args.label)
                data["map_id"] = map_id
                data["map_name"] = state.get("map_name")
                data["sessions"].append({
                    "started_at": session_started,
                    "label": args.label,
                })
                last_pos = None
                last_block_signature = None
                print(f"\nRecording to: {output_path}")

            now = time.strftime("%Y-%m-%dT%H:%M:%S")
            if pos != last_pos:
                x, y = pos
                record_step(data, x, y, now)
                data["path"].append({"x": x, "y": y, "t": now})
                if len(data["path"]) > max(0, args.path_limit):
                    data["path"] = data["path"][-args.path_limit:]
                last_pos = pos

                sys.stdout.write("\033[H\033[J")
                print("=" * 72)
                print(f"MAP: {state.get('map_name', 'Unknown')} ({map_id:02X})")
                print(f"LABEL: {data.get('label') or '-'}")
                print(f"POS: {x}, {y}")
                print(f"VISITED TILES: {len(data['visited_tiles'])}")
                print(f"BLOCKED EDGES: {len(data['blocked_edges'])}")
                print(f"BOUNDS: {data['bounds']}")
                print(f"OUTPUT: {output_path}")
                print("=" * 72)

            raw_blocking_value = state.get("dungeon_blocking", 255)
            blocking_value = int(raw_blocking_value if raw_blocking_value is not None else 255)
            blocked_direction = BLOCKING_TO_DIRECTION.get(blocking_value)
            if blocked_direction:
                x, y = pos
                block_signature = (x, y, blocked_direction)
                if block_signature != last_block_signature:
                    record_blocked_edge(data, x, y, blocked_direction, now)
                    last_block_signature = block_signature
            else:
                last_block_signature = None

            if time.time() - last_saved >= max(0.2, args.save_every):
                save_record(output_path, data)
                last_saved = time.time()

            time.sleep(max(0.02, args.poll))
    except KeyboardInterrupt:
        print("\nStopping shadow mapper...")
    finally:
        if current_output and data is not None:
            save_record(current_output, data)
        if helper_proc is not None:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(helper_proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            except Exception:
                try:
                    helper_proc.terminate()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
