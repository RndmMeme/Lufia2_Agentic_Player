#!/usr/bin/env python3
"""Generate offline-curatable grids for every original dungeon map image."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

try:
    from tools.build_dungeon_navigation_map import (
        build_map,
        draw_coordinate_grid,
        draw_navigation_preview,
        load_annotations,
    )
except ModuleNotFoundError:
    # Direct execution: python tools\build_all_dungeon_navigation_maps.py
    from build_dungeon_navigation_map import (
        build_map,
        draw_coordinate_grid,
        draw_navigation_preview,
        load_annotations,
    )


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}
REGISTERED_DUNGEONS = {"Secret_Skills_Cave": "room_landmarks"}


def original_images(folder: Path) -> list[Path]:
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def ensure_annotations(path: Path, dungeon: str) -> None:
    if path.exists():
        return
    path.write_text(
        json.dumps(
            {
                "schema": "lufia2-dungeon-annotations-v2",
                "dungeon": dungeon,
                "annotations": {},
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def write_index(root: Path, records: list[dict]) -> None:
    (root / "navigation_index.json").write_text(
        json.dumps(
            {
                "schema": "lufia2-dungeon-navigation-index-v1",
                "dungeon_count": len(records),
                "records": records,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    csv_fields = [
        "dungeon",
        "source_image",
        "image_width",
        "image_height",
        "grid_width",
        "grid_height",
        "runtime_alignment",
        "review_status",
        "grid_coordinates",
        "annotations",
    ]
    with (root / "navigation_index.csv").open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        writer.writeheader()
        writer.writerows(
            {field: record[field] for field in csv_fields}
            for record in records
        )

    lines = [
        "# Dungeon navigation map index",
        "",
        "All coordinates refer to the image tile grid. Only entries marked",
        "`direct` are already proven to match live WRAM tile coordinates.",
        "",
        "| Dungeon | Grid | WRAM alignment | Review status |",
        "|---|---:|---|---|",
    ]
    for record in records:
        lines.append(
            f"| {record['dungeon']} | "
            f"{record['grid_width']}x{record['grid_height']} | "
            f"{record['runtime_alignment']} | "
            f"{record['review_status']} |"
        )
    (root / "NAVIGATION_INDEX.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    template = root / "curation_list_template.csv"
    if not template.exists():
        with template.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "dungeon",
                    "coordinate",
                    "traversal",
                    "object",
                    "required_action",
                    "notes",
                ]
            )
            writer.writerow(
                [
                    "Secret_Skills_Cave",
                    "BK7",
                    "conditional",
                    "bush",
                    "sword",
                    "example row - delete or replace",
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build navigation grids for all dungeon source images."
    )
    parser.add_argument(
        "--root",
        default="emulator/maps/Dungeons",
        help="Dungeon directory root.",
    )
    parser.add_argument("--overlay-scale", type=int, default=2)
    parser.add_argument("--black-threshold", type=int, default=8)
    parser.add_argument(
        "--dungeon",
        action="append",
        help=(
            "Build only the named dungeon folder. May be repeated. "
            "A filtered build leaves the global index unchanged."
        ),
    )
    args = parser.parse_args()

    root = Path(args.root)
    records = []
    folders = sorted(path for path in root.iterdir() if path.is_dir())
    if args.dungeon:
        selected = set(args.dungeon)
        folders = [folder for folder in folders if folder.name in selected]
        missing = selected - {folder.name for folder in folders}
        if missing:
            raise ValueError(
                "Unknown dungeon folder(s): " + ", ".join(sorted(missing))
            )
    for index, folder in enumerate(folders, start=1):
        images = original_images(folder)
        if not images:
            print(f"[{index}/{len(folders)}] SKIP {folder.name}: no source image", flush=True)
            continue
        if len(images) != 1:
            print(
                f"[{index}/{len(folders)}] SKIP {folder.name}: "
                f"{len(images)} ambiguous source images",
                flush=True,
            )
            continue

        source = images[0]
        alignment = REGISTERED_DUNGEONS.get(folder.name, "unverified")
        annotation_path = folder / "annotations.json"
        ensure_annotations(annotation_path, folder.name)
        annotations = load_annotations(annotation_path)
        output_dir = folder / "navigation"
        output_dir.mkdir(parents=True, exist_ok=True)

        print(
            f"[{index}/{len(folders)}] BUILD {folder.name}: {source.name}",
            flush=True,
        )
        payload, padded = build_map(
            source,
            black_threshold=args.black_threshold,
            annotations=annotations,
            runtime_alignment=alignment,
        )
        payload["dungeon"] = folder.name
        payload["review_status"] = {
            "direct": "runtime_registered_needs_object_curation",
            "room_landmarks": "room_landmarks_registered_global_projection_forbidden",
        }.get(alignment, "needs_runtime_registration_and_object_curation")
        (output_dir / "navigation_map.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output_dir / "navigation_map.txt").write_text(
            "\n".join(payload["rows"]) + "\n",
            encoding="utf-8",
        )
        (output_dir / "object_map.txt").write_text(
            "\n".join(payload["object_rows"]) + "\n",
            encoding="utf-8",
        )
        draw_coordinate_grid(
            padded,
            payload,
            scale=args.overlay_scale,
        ).save(output_dir / "grid_coordinates.png")
        draw_navigation_preview(
            padded,
            payload,
            scale=args.overlay_scale,
        ).save(output_dir / "navigation_preview.png")

        grid = payload["grid"]
        records.append(
            {
                "dungeon": folder.name,
                "source_image": str(source),
                "image_width": grid["source_width_px"],
                "image_height": grid["source_height_px"],
                "grid_width": grid["width"],
                "grid_height": grid["height"],
                "runtime_alignment": alignment,
                "review_status": payload["review_status"],
                "grid_coordinates": str(output_dir / "grid_coordinates.png"),
                "annotations": str(annotation_path),
            }
        )

    if not args.dungeon:
        write_index(root, records)
    print(f"Built {len(records)} dungeon navigation packs in {root.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
