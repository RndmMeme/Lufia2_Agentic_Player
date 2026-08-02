import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


TILE_SIZE = 16


def is_content(pixel, black_threshold=8):
    r, g, b = pixel[:3]
    return r > black_threshold or g > black_threshold or b > black_threshold


def natural_key(name):
    parts = []
    token = ""
    is_digit = None
    for ch in name:
        if ch.isdigit():
            if is_digit is False:
                parts.append(token)
                token = ch
            else:
                token += ch
            is_digit = True
        else:
            if is_digit is True:
                parts.append(int(token))
                token = ch
            else:
                token += ch
            is_digit = False
    if token:
        parts.append(int(token) if is_digit else token)
    return parts


def match_labeled_files(room_dir: Path, manifest: dict):
    segment_by_scaled_size = {}
    scale = int(manifest.get("scale", 1))
    for segment in manifest.get("segments", []):
        padded = segment["padded_bbox"]
        key = ((padded["max_x"] - padded["min_x"] + 1) * scale, (padded["max_y"] - padded["min_y"] + 1) * scale)
        segment_by_scaled_size.setdefault(key, []).append(segment)

    labeled_files = [
        path for path in room_dir.glob("*.png")
        if path.name != "segments_manifest.json"
    ]
    labeled_files.sort(key=lambda path: natural_key(path.stem))

    mapping = {}
    for path in labeled_files:
        img = Image.open(path)
        key = img.size
        candidates = segment_by_scaled_size.get(key, [])
        if not candidates:
            raise RuntimeError(f"No matching segment found for {path.name} with size {img.size}")
        segment = candidates.pop(0)
        mapping[path.name] = segment
    return mapping


def detect_portals(source_image: Image.Image, bbox: dict, black_threshold=8, min_run=3):
    pixels = source_image.load()
    min_x = bbox["min_x"]
    min_y = bbox["min_y"]
    max_x = bbox["max_x"]
    max_y = bbox["max_y"]
    portals = []

    def add_runs(side, values):
        run_start = None
        for idx, is_open in enumerate(values + [False]):
            if is_open and run_start is None:
                run_start = idx
            elif not is_open and run_start is not None:
                run_end = idx - 1
                if run_end - run_start + 1 >= min_run:
                    center = (run_start + run_end) // 2
                    if side in ("north", "south"):
                        portals.append({
                            "side": side,
                            "x": min_x + center,
                            "y": min_y if side == "north" else max_y,
                            "span_start": min_x + run_start,
                            "span_end": min_x + run_end,
                        })
                    else:
                        portals.append({
                            "side": side,
                            "x": min_x if side == "west" else max_x,
                            "y": min_y + center,
                            "span_start": min_y + run_start,
                            "span_end": min_y + run_end,
                        })
                run_start = None

    north = [is_content(pixels[x, min_y], black_threshold) for x in range(min_x, max_x + 1)]
    south = [is_content(pixels[x, max_y], black_threshold) for x in range(min_x, max_x + 1)]
    west = [is_content(pixels[min_x, y], black_threshold) for y in range(min_y, max_y + 1)]
    east = [is_content(pixels[max_x, y], black_threshold) for y in range(min_y, max_y + 1)]
    add_runs("north", north)
    add_runs("south", south)
    add_runs("west", west)
    add_runs("east", east)
    return portals


def infer_connections(rooms):
    opposite = {"north": "south", "south": "north", "west": "east", "east": "west"}
    pairs = []
    used = set()

    for a in rooms:
        for b in rooms:
            if a["id"] == b["id"]:
                continue
            for pa in a["portals"]:
                for pb in b["portals"]:
                    if pb["side"] != opposite[pa["side"]]:
                        continue
                    if pa["side"] in ("east", "west"):
                        gap = abs(pb["x"] - pa["x"])
                        lane_delta = abs(pb["y"] - pa["y"])
                        facing_gap = abs(b["bbox"]["min_x"] - a["bbox"]["max_x"]) if pa["side"] == "east" else abs(a["bbox"]["min_x"] - b["bbox"]["max_x"])
                    else:
                        gap = abs(pb["y"] - pa["y"])
                        lane_delta = abs(pb["x"] - pa["x"])
                        facing_gap = abs(b["bbox"]["min_y"] - a["bbox"]["max_y"]) if pa["side"] == "south" else abs(a["bbox"]["min_y"] - b["bbox"]["max_y"])
                    if lane_delta > 48 or facing_gap > 140:
                        continue
                    key = tuple(sorted((a["id"], b["id"])))
                    score = facing_gap + lane_delta
                    pairs.append({
                        "key": key,
                        "from_room": a["id"],
                        "to_room": b["id"],
                        "from_side": pa["side"],
                        "to_side": pb["side"],
                        "from_point": {"x": pa["x"], "y": pa["y"]},
                        "to_point": {"x": pb["x"], "y": pb["y"]},
                        "score": score,
                        "method": "portal",
                    })

    # Fallback: if explicit portal matching is weak/missing, connect nearby rooms/connectors
    # that are clearly adjacent in the original source sheet.
    for a in rooms:
        for b in rooms:
            if a["id"] == b["id"]:
                continue
            key = tuple(sorted((a["id"], b["id"])))
            ax1, ay1, ax2, ay2 = a["bbox"]["min_x"], a["bbox"]["min_y"], a["bbox"]["max_x"], a["bbox"]["max_y"]
            bx1, by1, bx2, by2 = b["bbox"]["min_x"], b["bbox"]["min_y"], b["bbox"]["max_x"], b["bbox"]["max_y"]

            horizontal_overlap = max(0, min(ax2, bx2) - max(ax1, bx1))
            vertical_overlap = max(0, min(ay2, by2) - max(ay1, by1))

            if bx1 >= ax2:
                gap = bx1 - ax2
                if gap <= 60 and vertical_overlap >= 20:
                    pairs.append({
                        "key": key,
                        "from_room": a["id"],
                        "to_room": b["id"],
                        "from_side": "east",
                        "to_side": "west",
                        "from_point": {"x": ax2, "y": (max(ay1, by1) + min(ay2, by2)) // 2},
                        "to_point": {"x": bx1, "y": (max(ay1, by1) + min(ay2, by2)) // 2},
                        "score": gap + max(0, 40 - vertical_overlap // 4),
                        "method": "bbox",
                    })
            if by1 >= ay2:
                gap = by1 - ay2
                if gap <= 60 and horizontal_overlap >= 20:
                    pairs.append({
                        "key": key,
                        "from_room": a["id"],
                        "to_room": b["id"],
                        "from_side": "south",
                        "to_side": "north",
                        "from_point": {"x": (max(ax1, bx1) + min(ax2, bx2)) // 2, "y": ay2},
                        "to_point": {"x": (max(ax1, bx1) + min(ax2, bx2)) // 2, "y": by1},
                        "score": gap + max(0, 40 - horizontal_overlap // 4),
                        "method": "bbox",
                    })

    pairs.sort(key=lambda item: item["score"])
    chosen = []
    for pair in pairs:
        key = pair["key"]
        if key in used:
            continue
        used.add(key)
        chosen.append({k: v for k, v in pair.items() if k != "key"})
    return chosen


def make_grid_overlay(image_path: Path, padded_bbox: dict, scale: int, output_path: Path):
    image = Image.open(image_path).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    step = TILE_SIZE * scale
    offset_x = ((TILE_SIZE - (padded_bbox["min_x"] % TILE_SIZE)) % TILE_SIZE) * scale
    offset_y = ((TILE_SIZE - (padded_bbox["min_y"] % TILE_SIZE)) % TILE_SIZE) * scale
    width, height = image.size

    for x in range(offset_x, width, step):
        draw.line((x, 0, x, height), fill=(80, 200, 255, 120), width=1)
    for y in range(offset_y, height, step):
        draw.line((0, y, width, y), fill=(80, 200, 255, 120), width=1)

    image.save(output_path)
    return {
        "image_tile_size": step,
        "grid_offset_x": offset_x,
        "grid_offset_y": offset_y,
    }


def build_tile_metadata(padded_bbox: dict, scale: int):
    min_tile_x = padded_bbox["min_x"] // TILE_SIZE
    min_tile_y = padded_bbox["min_y"] // TILE_SIZE
    max_tile_x = padded_bbox["max_x"] // TILE_SIZE
    max_tile_y = padded_bbox["max_y"] // TILE_SIZE
    return {
        "tile_size_world": TILE_SIZE,
        "tile_size_image": TILE_SIZE * scale,
        "global_tile_bounds": {
            "min_x": min_tile_x,
            "min_y": min_tile_y,
            "max_x": max_tile_x,
            "max_y": max_tile_y,
            "width": max_tile_x - min_tile_x + 1,
            "height": max_tile_y - min_tile_y + 1,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Build tile-grid overlays and room graph metadata from labeled dungeon room images.")
    parser.add_argument("room_dir", help="Directory containing labeled room/connector PNGs and segments_manifest.json")
    parser.add_argument("--output-dir", help="Output directory. Defaults to <room_dir>/grid_pack")
    parser.add_argument("--black-threshold", type=int, default=8)
    args = parser.parse_args()

    room_dir = Path(args.room_dir)
    manifest_path = room_dir / "segments_manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_image = Image.open(Path(manifest["source_image"])).convert("RGB")
    scale = int(manifest.get("scale", 1))

    output_dir = Path(args.output_dir) if args.output_dir else room_dir / "grid_pack"
    overlays_dir = output_dir / "overlays"
    room_json_dir = output_dir / "rooms"
    overlays_dir.mkdir(parents=True, exist_ok=True)
    room_json_dir.mkdir(parents=True, exist_ok=True)

    mapping = match_labeled_files(room_dir, manifest)
    rooms = []

    for filename, segment in sorted(mapping.items(), key=lambda item: natural_key(Path(item[0]).stem)):
        image_path = room_dir / filename
        room_id = Path(filename).stem
        padded_bbox = segment["padded_bbox"]
        bbox = segment["bbox"]
        overlay_meta = make_grid_overlay(image_path, padded_bbox, scale, overlays_dir / filename)
        tile_meta = build_tile_metadata(padded_bbox, scale)
        portals = detect_portals(source_image, bbox, black_threshold=args.black_threshold)

        room_record = {
            "id": room_id,
            "kind": "connector" if room_id.startswith("connector_") else "room",
            "image": filename,
            "overlay_image": filename,
            "source_segment_id": segment["id"],
            "pixel_count": segment["pixel_count"],
            "bbox": bbox,
            "padded_bbox": padded_bbox,
            "grid": {**overlay_meta, **tile_meta},
            "portals": portals,
        }
        rooms.append(room_record)
        (room_json_dir / f"{room_id}.json").write_text(json.dumps(room_record, indent=2), encoding="utf-8")

    connections = infer_connections(rooms)
    pack = {
        "source_image": manifest["source_image"],
        "scale": scale,
        "rooms": rooms,
        "connections": connections,
    }
    (output_dir / "room_pack.json").write_text(json.dumps(pack, indent=2), encoding="utf-8")

    print(f"Built room pack in {output_dir}")
    print(f"Rooms: {len(rooms)}")
    print(f"Connections inferred: {len(connections)}")


if __name__ == "__main__":
    main()
