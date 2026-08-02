#!/usr/bin/env python3
"""Compile manual dungeon markers into navigation semantics and QA reports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


MARKER_SCHEMA = "lufia2-dungeon-curation-markers-v1"
COMPILED_SCHEMA = "lufia2-compiled-dungeon-curation-v1"
VALIDATION_SCHEMA = "lufia2-dungeon-curation-validation-v1"
OVERRIDE_SCHEMA = "lufia2-dungeon-navigation-overrides-v1"
GRID_SIZE = 16
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}
VALID_TRAVERSAL = {
    "blocked",
    "conditional",
    "confirmed_walkable",
    "unverified",
    "unknown",
}


@dataclass(frozen=True)
class TypeRule:
    layer: str
    default_symbol: str
    allowed_traversal: frozenset[str]
    role: str


TYPE_RULES = {
    "walkable": TypeRule(
        "terrain", "o", frozenset({"confirmed_walkable", "conditional", "blocked"}), "floor"
    ),
    "blocked": TypeRule(
        "terrain", "#", frozenset({"blocked", "conditional", "confirmed_walkable"}), "obstacle"
    ),
    "wall": TypeRule("terrain", "W", frozenset({"blocked"}), "wall"),
    "water": TypeRule("terrain", "~", frozenset({"blocked"}), "hazard"),
    "lava": TypeRule("terrain", "^", frozenset({"blocked"}), "hazard"),
    "door": TypeRule(
        "transition",
        "D",
        frozenset({"confirmed_walkable", "conditional", "blocked"}),
        "north_south_transition",
    ),
    "stairs": TypeRule(
        "transition",
        "T",
        frozenset({"confirmed_walkable", "conditional"}),
        "four_side_transition",
    ),
    "ladder": TypeRule(
        "transition", "H", frozenset({"confirmed_walkable"}), "vertical_path"
    ),
    "bush": TypeRule(
        "occupancy", "b", frozenset({"conditional", "blocked"}), "removable_obstacle"
    ),
    "chest": TypeRule(
        "occupancy",
        "C",
        frozenset({"blocked", "conditional", "confirmed_walkable"}),
        "interactable_obstacle",
    ),
    "monster": TypeRule(
        "occupancy",
        "M",
        frozenset({"conditional", "blocked", "confirmed_walkable"}),
        "dynamic_obstacle",
    ),
    "npc": TypeRule(
        "occupancy",
        "N",
        frozenset({"conditional", "confirmed_walkable"}),
        "dynamic_obstacle",
    ),
    "switch": TypeRule(
        "mechanism",
        "s",
        frozenset({"conditional", "confirmed_walkable", "blocked"}),
        "mechanism",
    ),
    "puzzle": TypeRule(
        "mechanism",
        "P",
        frozenset({"conditional", "confirmed_walkable", "blocked"}),
        "puzzle",
    ),
}

HARD_TERRAIN = {"blocked", "wall", "water", "lava"}
PASSABLE_TYPES = {"walkable", "door", "stairs", "ladder"}
CONDITIONAL_TYPES = {"bush", "chest", "monster", "npc", "switch", "puzzle"}
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def original_image(folder: Path) -> Path:
    images = sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if len(images) != 1:
        raise ValueError(
            f"{folder.name}: expected one source image, found {len(images)}"
        )
    return images[0]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def column_label(x: int) -> str:
    result = ""
    value = x + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def coordinate(x: int, y: int) -> str:
    return f"{column_label(x)}{y + 1}"


def marker_center(marker: dict) -> tuple[float, float]:
    return (
        marker["x_px"] + marker["width_px"] / 2,
        marker["y_px"] + marker["height_px"] / 2,
    )


def anchor_cell(marker: dict) -> tuple[int, int]:
    center_x, center_y = marker_center(marker)
    return int(center_x // GRID_SIZE), int(center_y // GRID_SIZE)


def intersected_cells(marker: dict) -> list[dict]:
    left = marker["x_px"]
    top = marker["y_px"]
    right = left + marker["width_px"]
    bottom = top + marker["height_px"]
    start_x = left // GRID_SIZE
    start_y = top // GRID_SIZE
    end_x = (right - 1) // GRID_SIZE
    end_y = (bottom - 1) // GRID_SIZE
    marker_area = marker["width_px"] * marker["height_px"]
    cells = []
    for y in range(start_y, end_y + 1):
        for x in range(start_x, end_x + 1):
            cell_left = x * GRID_SIZE
            cell_top = y * GRID_SIZE
            overlap_width = max(
                0,
                min(right, cell_left + GRID_SIZE) - max(left, cell_left),
            )
            overlap_height = max(
                0,
                min(bottom, cell_top + GRID_SIZE) - max(top, cell_top),
            )
            area = overlap_width * overlap_height
            if area:
                cells.append(
                    {
                        "x": x,
                        "y": y,
                        "coordinate": coordinate(x, y),
                        "overlap_px": area,
                        "cell_coverage": round(area / (GRID_SIZE * GRID_SIZE), 4),
                        "marker_coverage": round(area / marker_area, 4),
                    }
                )
    return cells


def primary_cells(marker: dict) -> list[dict]:
    cells = intersected_cells(marker)
    primary = [cell for cell in cells if cell["cell_coverage"] >= 0.5]
    if primary:
        return primary
    anchor_x, anchor_y = anchor_cell(marker)
    for cell in cells:
        if cell["x"] == anchor_x and cell["y"] == anchor_y:
            return [cell]
    return cells[:1]


def issue(
    severity: str,
    code: str,
    message: str,
    marker_ids: list[str] | None = None,
    coordinates: list[str] | None = None,
    suggested_fix: str | None = None,
) -> dict:
    finding = {
        "severity": severity,
        "code": code,
        "message": message,
        "marker_ids": marker_ids or [],
        "coordinates": coordinates or [],
    }
    if suggested_fix:
        finding["suggested_fix"] = suggested_fix
    return finding


def validate_marker_fields(marker: dict, image_size: tuple[int, int]) -> list[dict]:
    findings = []
    marker_id = marker.get("id") or "<missing>"
    marker_type = marker.get("type")
    if marker_type not in TYPE_RULES:
        findings.append(
            issue("error", "unknown_type", f"Unknown marker type {marker_type!r}.", [marker_id])
        )
        return findings
    rule = TYPE_RULES[marker_type]
    traversal = marker.get("traversal")
    if traversal not in VALID_TRAVERSAL:
        findings.append(
            issue(
                "error",
                "invalid_traversal",
                f"Invalid traversal {traversal!r} for {marker_type}.",
                [marker_id],
            )
        )
    elif traversal not in rule.allowed_traversal:
        findings.append(
            issue(
                "warning",
                "unusual_traversal",
                f"{marker_type} normally does not use traversal {traversal!r}.",
                [marker_id],
            )
        )

    geometry = tuple(marker.get(key) for key in ("x_px", "y_px", "width_px", "height_px"))
    if not all(isinstance(value, int) for value in geometry):
        findings.append(issue("error", "invalid_geometry", "Geometry must contain integers.", [marker_id]))
        return findings
    x, y, width, height = geometry
    image_width, image_height = image_size
    marker_coordinate = [coordinate(*anchor_cell(marker))]
    if width <= 0 or height <= 0:
        findings.append(issue("error", "invalid_size", "Marker size must be positive.", [marker_id]))
    if x < 0 or y < 0 or x + width > image_width or y + height > image_height:
        findings.append(
            issue("error", "out_of_bounds", f"Marker box {geometry} is outside {image_size}.", [marker_id])
        )
    snap = marker.get("snap_px")
    if snap not in {1, 8, 16}:
        findings.append(issue("warning", "unusual_snap", f"Unexpected snap value {snap!r}.", [marker_id]))

    # These are technically accepted by the editor, but are likely accidental
    # because their names directly contradict their traversal state.
    if marker_type == "walkable" and traversal == "blocked":
        findings.append(
            issue(
                "warning",
                "walkable_marked_blocked",
                "Walkable marker is marked blocked.",
                [marker_id],
                marker_coordinate,
                suggested_fix="Set traversal to confirmed_walkable, or change the marker type.",
            )
        )
    if marker_type == "blocked" and traversal == "confirmed_walkable":
        findings.append(
            issue(
                "warning",
                "blocked_marked_walkable",
                "Blocked marker is marked confirmed_walkable.",
                [marker_id],
                marker_coordinate,
                suggested_fix="Set traversal to blocked, or change the marker type.",
            )
        )
    if marker_type == "chest" and traversal == "confirmed_walkable":
        findings.append(
            issue(
                "warning",
                "chest_marked_walkable",
                "Chest occupancy is marked confirmed_walkable.",
                [marker_id],
                marker_coordinate,
                suggested_fix="Verify whether the opened chest tile is passable; otherwise set traversal to blocked.",
            )
        )
    return findings


def terrain_conflict(types: set[str]) -> bool:
    if "walkable" in types and types & HARD_TERRAIN:
        return True
    if "water" in types and "lava" in types:
        return True
    return False


def connected_components(cells: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(cells)
    components = []
    while remaining:
        seed = remaining.pop()
        component = {seed}
        pending = deque([seed])
        while pending:
            x, y = pending.popleft()
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    pending.append(neighbor)
        components.append(component)
    return sorted(components, key=len, reverse=True)


def resolve_cell(contributions: list[dict]) -> dict:
    types = {item["type"] for item in contributions}
    traversals = {item["traversal"] for item in contributions}
    terrain = sorted(types & {"walkable", "blocked", "wall", "water", "lava"})
    objects = sorted(types - set(terrain))

    if "lava" in types:
        terrain_state = "lava"
    elif "water" in types:
        terrain_state = "water"
    elif types & {"blocked", "wall"}:
        terrain_state = "blocked"
    elif "walkable" in types:
        terrain_state = "walkable"
    else:
        terrain_state = "unknown"

    if terrain_conflict(types):
        effective = "conflict"
    elif terrain_state in {"lava", "water", "blocked"}:
        effective = "blocked"
    elif "blocked" in traversals:
        effective = "blocked"
    elif "conditional" in traversals or types & CONDITIONAL_TYPES:
        effective = "conditional"
    elif "confirmed_walkable" in traversals or types & PASSABLE_TYPES:
        effective = "confirmed_walkable"
    else:
        effective = "unknown"

    symbol_priority = [
        "door",
        "stairs",
        "ladder",
        "npc",
        "monster",
        "bush",
        "chest",
        "switch",
        "puzzle",
        "lava",
        "water",
        "wall",
        "blocked",
        "walkable",
    ]
    symbol_type = next((name for name in symbol_priority if name in types), None)
    symbol = TYPE_RULES[symbol_type].default_symbol if symbol_type else "?"
    return {
        "terrain": terrain,
        "objects": objects,
        "effective_traversal": effective,
        "symbol": symbol,
        "conflict": terrain_conflict(types),
    }


def compile_dungeon(folder: Path) -> tuple[dict, dict]:
    marker_path = folder / "curation_markers.json"
    source_path = original_image(folder)
    marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
    if marker_payload.get("schema") != MARKER_SCHEMA:
        raise ValueError(f"{folder.name}: unsupported marker schema")
    markers = marker_payload.get("markers", [])
    with Image.open(source_path) as image:
        image_size = image.size
    width_cells = math.ceil(image_size[0] / GRID_SIZE)
    height_cells = math.ceil(image_size[1] / GRID_SIZE)

    findings = []
    ids = set()
    compiled_markers = []
    exact_boxes = defaultdict(list)
    center_buckets = defaultdict(list)
    cell_contributions: dict[tuple[int, int], list[dict]] = defaultdict(list)
    override_path = folder / "curation_navigation_overrides.json"
    projection_overrides: dict[str, dict] = {}
    if override_path.exists():
        override_payload = json.loads(override_path.read_text(encoding="utf-8"))
        if override_payload.get("schema") != OVERRIDE_SCHEMA:
            raise ValueError(f"{folder.name}: unsupported navigation override schema")
        for override in override_payload.get("cells", []):
            cell_coordinate = override.get("coordinate")
            traversal = override.get("effective_traversal")
            if not isinstance(cell_coordinate, str) or cell_coordinate in projection_overrides:
                findings.append(
                    issue("error", "invalid_navigation_override", f"Invalid or duplicate override coordinate {cell_coordinate!r}.")
                )
                continue
            if traversal not in {"blocked", "conditional", "confirmed_walkable", "partial", "unknown"}:
                findings.append(
                    issue("error", "invalid_navigation_override", f"Invalid override traversal {traversal!r} at {cell_coordinate}.", coordinates=[cell_coordinate])
                )
                continue
            projection_overrides[cell_coordinate] = override

    for marker in markers:
        marker_id = marker.get("id")
        if not marker_id or marker_id in ids:
            findings.append(
                issue("error", "duplicate_or_missing_id", f"Invalid marker id {marker_id!r}.", [marker_id or "<missing>"])
            )
        ids.add(marker_id)
        findings.extend(validate_marker_fields(marker, image_size))
        if marker.get("type") not in TYPE_RULES:
            continue
        geometry = (marker["x_px"], marker["y_px"], marker["width_px"], marker["height_px"])
        exact_boxes[geometry].append(marker)
        center = marker_center(marker)
        center_buckets[(round(center[0], 4), round(center[1], 4))].append(marker)
        anchor_x, anchor_y = anchor_cell(marker)
        touched = intersected_cells(marker)
        primary = primary_cells(marker)
        rule = TYPE_RULES[marker["type"]]
        compiled_marker = {
            **marker,
            "layer": rule.layer,
            "role": rule.role,
            "center_px": {"x": center[0], "y": center[1]},
            "anchor_cell": {
                "x": anchor_x,
                "y": anchor_y,
                "coordinate": coordinate(anchor_x, anchor_y),
            },
            "primary_cells": primary,
            "touched_cells": touched,
        }
        compiled_markers.append(compiled_marker)
        for cell in primary:
            cell_contributions[(cell["x"], cell["y"])].append(
                {
                    "marker_id": marker_id,
                    "type": marker["type"],
                    "traversal": marker.get("traversal"),
                    "cell_coverage": cell["cell_coverage"],
                    "source": marker.get("source"),
                }
            )

    for geometry, group in exact_boxes.items():
        if len(group) < 2:
            continue
        same_types = Counter(marker["type"] for marker in group)
        duplicate_types = [name for name, count in same_types.items() if count > 1]
        if duplicate_types:
            findings.append(
                issue(
                    "error",
                    "exact_duplicate",
                    f"Exact duplicate box {geometry} for type(s) {duplicate_types}.",
                    [marker["id"] for marker in group],
                    [coordinate(*anchor_cell(group[0]))],
                )
            )
        types = set(same_types)
        if terrain_conflict(types):
            findings.append(
                issue(
                    "error",
                    "exact_terrain_conflict",
                    f"Conflicting terrain types {sorted(types)} share box {geometry}.",
                    [marker["id"] for marker in group],
                    [coordinate(*anchor_cell(group[0]))],
                )
            )

    # Same-center cross-layer overlays are intentional (for example a switch
    # hidden under a bush). Only terrain contradictions are errors.
    for center, group in center_buckets.items():
        if len(group) > 1 and terrain_conflict({marker["type"] for marker in group}):
            findings.append(
                issue(
                    "error",
                    "center_terrain_conflict",
                    f"Conflicting terrain markers share center {center}.",
                    [marker["id"] for marker in group],
                    [coordinate(*anchor_cell(group[0]))],
                )
            )

    stair_markers = [marker for marker in markers if marker.get("type") == "stairs"]
    external_stairs = [
        marker
        for marker in stair_markers
        if any(word in str(marker.get("notes", "")).lower() for word in ("entrance", "exit"))
    ]
    internal_stair_count = len(stair_markers) - len(external_stairs)
    # An even total can already be paired. For an odd total, one (or another
    # odd number) explicitly labelled external endpoint explains the parity.
    if len(stair_markers) % 2 and len(external_stairs) % 2 == 0:
        findings.append(
            issue(
                "warning",
                "odd_stair_count",
                f"Dungeon has {len(stair_markers)} stair endpoints, including "
                f"{len(external_stairs)} labelled external endpoint(s); the remaining "
                f"{internal_stair_count} internal endpoints are odd.",
                [marker["id"] for marker in stair_markers],
                suggested_fix="Label a legitimate external endpoint with 'entrance' or 'exit', or add the missing stair endpoint.",
            )
        )

    compiled_cells = []
    passable_cells = set()
    projection_conflicts = 0
    resolved_projection_conflicts = 0
    used_overrides = set()
    for (x, y), contributions in sorted(cell_contributions.items(), key=lambda item: (item[0][1], item[0][0])):
        resolved = resolve_cell(contributions)
        cell_coordinate = coordinate(x, y)
        raw_conflict = resolved["conflict"]
        override = projection_overrides.get(cell_coordinate)
        if override:
            used_overrides.add(cell_coordinate)
            resolved = {
                **resolved,
                "raw_effective_traversal": resolved["effective_traversal"],
                "raw_conflict": raw_conflict,
                "effective_traversal": override["effective_traversal"],
                "conflict": False,
                "navigation_override": override,
            }
            if raw_conflict:
                resolved_projection_conflicts += 1
        elif raw_conflict:
            projection_conflicts += 1
        if resolved["effective_traversal"] in {"confirmed_walkable", "conditional", "partial"}:
            passable_cells.add((x, y))
        compiled_cells.append(
            {
                "x": x,
                "y": y,
                "coordinate": cell_coordinate,
                "contributions": contributions,
                **resolved,
            }
        )

    for unused_coordinate in sorted(set(projection_overrides) - used_overrides):
        findings.append(
            issue(
                "error",
                "unused_navigation_override",
                "Navigation override does not reference a compiled marker cell.",
                coordinates=[unused_coordinate],
            )
        )

    projection_conflict_cells = [cell for cell in compiled_cells if cell["conflict"]]
    if projection_conflict_cells:
        conflict_marker_ids = sorted(
            {
                contribution["marker_id"]
                for cell in projection_conflict_cells
                for contribution in cell["contributions"]
            }
        )
        findings.append(
            issue(
                "info",
                "grid_projection_overlap",
                f"{len(projection_conflict_cells)} 16x16 reference cell(s) contain portions of "
                "conflicting terrain. Exact pixel boxes remain authoritative.",
                conflict_marker_ids,
                [cell["coordinate"] for cell in projection_conflict_cells],
            )
        )

    components = connected_components(passable_cells)
    rows = [["?" for _ in range(width_cells)] for _ in range(height_cells)]
    for cell in compiled_cells:
        rows[cell["y"]][cell["x"]] = cell["symbol"]

    severity_counts = Counter(item["severity"] for item in findings)
    code_counts = Counter(item["code"] for item in findings)
    compiled = {
        "schema": COMPILED_SCHEMA,
        "dungeon": folder.name,
        "source_image": source_path.name,
        "source_image_sha256": sha256_file(source_path),
        "marker_source": marker_path.name,
        "marker_source_sha256": sha256_file(marker_path),
        "grid": {
            "reference_cell_px": GRID_SIZE,
            "width": width_cells,
            "height": height_cells,
            "projection": (
                "Exact pixel boxes are authoritative. A marker contributes to every "
                "16x16 cell covered by at least 50%; when none reaches 50%, its "
                "center/anchor cell is used."
            ),
        },
        "object_rules": {
            name: {
                "layer": rule.layer,
                "role": rule.role,
                "symbol": rule.default_symbol,
                "allowed_traversal": sorted(rule.allowed_traversal),
            }
            for name, rule in TYPE_RULES.items()
        },
        "markers": compiled_markers,
        "cells": compiled_cells,
        "ascii_rows": ["".join(row) for row in rows],
        "topology": {
            "passable_or_conditional_primary_cells": len(passable_cells),
            "connected_components": len(components),
            "component_sizes": [len(component) for component in components],
            "projection_conflict_cells": projection_conflicts,
            "resolved_projection_conflict_cells": resolved_projection_conflicts,
            "note": "Components describe curated primary cells only, not unmarked visual floor.",
        },
        "navigation_overrides": {
            "source": override_path.name if override_path.exists() else None,
            "source_sha256": sha256_file(override_path) if override_path.exists() else None,
            "cells": list(projection_overrides.values()),
        },
    }
    validation = {
        "schema": VALIDATION_SCHEMA,
        "dungeon": folder.name,
        "marker_count": len(markers),
        "type_counts": dict(Counter(marker.get("type") for marker in markers)),
        "severity_counts": {key: severity_counts.get(key, 0) for key in ("error", "warning", "info")},
        "code_counts": dict(code_counts),
        "findings": sorted(
            findings,
            key=lambda item: (SEVERITY_ORDER[item["severity"]], item["code"], item["marker_ids"]),
        ),
    }
    return compiled, validation


def draw_validation_overlay(folder: Path, validation: dict, compiled: dict) -> Image.Image:
    image = Image.open(original_image(folder)).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    try:
        font = ImageFont.truetype("arial.ttf", 11)
    except OSError:
        font = ImageFont.load_default()
    markers = {marker["id"]: marker for marker in compiled["markers"]}
    colors = {"error": (255, 40, 55, 255), "warning": (255, 190, 30, 255), "info": (70, 190, 255, 255)}
    for finding in validation["findings"]:
        color = colors[finding["severity"]]
        for marker_id in finding["marker_ids"]:
            marker = markers.get(marker_id)
            if not marker:
                continue
            x = marker["x_px"]
            y = marker["y_px"]
            right = x + marker["width_px"] - 1
            bottom = y + marker["height_px"] - 1
            draw.rectangle((x - 2, y - 2, right + 2, bottom + 2), outline=color, width=2)
            draw.text((x, max(0, y - 12)), finding["code"], font=font, fill=color, stroke_width=1, stroke_fill=(0, 0, 0, 255))
    return Image.alpha_composite(image, overlay).convert("RGB")


def review_candidates(records: list[dict]) -> list[dict]:
    """Return geometry that may still require human review."""
    candidates = []
    for record in records:
        compiled = record["compiled"]
        dungeon = compiled["dungeon"]
        markers = compiled["markers"]
        # With 8px placement, 50% overlaps are routine. At 75% or more,
        # same-type/same-size boxes may be accidental duplicate clicks and are
        # worth listing for review. Overlapping hard blocked terrain merely
        # provides redundant coverage and is intentionally ignored.
        for index, first in enumerate(markers):
            first_box = (first["x_px"], first["y_px"], first["width_px"], first["height_px"])
            for second in markers[index + 1 :]:
                if first["type"] != second["type"]:
                    continue
                if (first["width_px"], first["height_px"]) != (second["width_px"], second["height_px"]):
                    continue
                second_box = (second["x_px"], second["y_px"], second["width_px"], second["height_px"])
                if first_box == second_box:
                    continue
                left = max(first["x_px"], second["x_px"])
                top = max(first["y_px"], second["y_px"])
                right = min(first["x_px"] + first["width_px"], second["x_px"] + second["width_px"])
                bottom = min(first["y_px"] + first["height_px"], second["y_px"] + second["height_px"])
                overlap = max(0, right - left) * max(0, bottom - top)
                area = first["width_px"] * first["height_px"]
                ratio = overlap / area
                if ratio >= 0.75:
                    if (
                        first["type"] in HARD_TERRAIN
                        and first["traversal"] == "blocked"
                        and second["traversal"] == "blocked"
                    ):
                        continue
                    candidates.append(
                        {
                            "category": "possible_near_duplicate",
                            "dungeon": dungeon,
                            "coordinates": f"{first['anchor_cell']['coordinate']};{second['anchor_cell']['coordinate']}",
                            "marker_ids": f"{first['id']};{second['id']}",
                            "type": first["type"],
                            "traversal": f"{first['traversal']};{second['traversal']}",
                            "details": f"Same-type boxes overlap by {ratio:.0%}; may be intentional tight coverage.",
                        }
                    )
    return candidates


def learning_backlog(records: list[dict]) -> list[dict]:
    """List conditional behavior intentionally left for the player to learn."""
    rows = []
    for record in records:
        dungeon = record["compiled"]["dungeon"]
        for marker in record["compiled"]["markers"]:
            if marker.get("traversal") != "conditional":
                continue
            if marker.get("required_action") or marker.get("notes"):
                continue
            rows.append(
                {
                    "dungeon": dungeon,
                    "coordinate": marker["anchor_cell"]["coordinate"],
                    "marker_id": marker["id"],
                    "type": marker["type"],
                    "learned_action": "",
                    "learned_notes": "",
                    "status": "discover_at_runtime",
                }
            )
    return rows


def write_review_reports(root: Path, records: list[dict]) -> None:
    candidates = review_candidates(records)
    category_counts = Counter(item["category"] for item in candidates)
    lines = [
        "# Dungeon curation review candidates",
        "",
        "These are geometry candidates only, not compiler errors. Conditional behavior without notes is intentionally learned at runtime and tracked separately.",
        "",
        f"- Total review rows: {len(candidates)}",
    ]
    for category, count in sorted(category_counts.items()):
        lines.append(f"- {category}: {count}")
    if not candidates:
        lines.append("- No unresolved geometry candidates.")
    (root / "CURATION_REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    with (root / "curation_review.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fieldnames = ["category", "dungeon", "coordinates", "marker_ids", "type", "traversal", "details"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(candidates)

    backlog = learning_backlog(records)
    backlog_types = Counter(item["type"] for item in backlog)
    backlog_lines = [
        "# Runtime navigation learning backlog",
        "",
        "These conditional markers intentionally have no prescribed action. The player should explore first, consult the walkthrough only when stuck, and persist learned notes for later runs.",
        "",
        f"- Total undiscovered actions: {len(backlog)}",
    ]
    for marker_type, count in sorted(backlog_types.items()):
        backlog_lines.append(f"- {marker_type}: {count}")
    (root / "CURATION_LEARNING_BACKLOG.md").write_text(
        "\n".join(backlog_lines) + "\n", encoding="utf-8"
    )
    with (root / "curation_learning_backlog.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        fieldnames = [
            "dungeon",
            "coordinate",
            "marker_id",
            "type",
            "learned_action",
            "learned_notes",
            "status",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(backlog)


def write_global_reports(root: Path, records: list[dict]) -> None:
    totals = Counter()
    codes = Counter()
    for record in records:
        totals.update(record["validation"]["severity_counts"])
        codes.update(record["validation"]["code_counts"])
    payload = {
        "schema": "lufia2-global-dungeon-curation-validation-v1",
        "dungeon_count": len(records),
        "marker_count": sum(record["validation"]["marker_count"] for record in records),
        "severity_counts": {key: totals.get(key, 0) for key in ("error", "warning", "info")},
        "code_counts": dict(codes),
        "dungeons": [record["validation"] for record in records],
    }
    (root / "curation_validation.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Dungeon curation validation",
        "",
        f"- Dungeons: {payload['dungeon_count']}",
        f"- Markers: {payload['marker_count']}",
        f"- Errors: {payload['severity_counts']['error']}",
        f"- Warnings: {payload['severity_counts']['warning']}",
        f"- Info: {payload['severity_counts']['info']}",
        "",
        "| Dungeon | Markers | Errors | Warnings | Info | Codes |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for record in records:
        validation = record["validation"]
        code_text = ", ".join(
            f"{code}={count}" for code, count in sorted(validation["code_counts"].items())
        ) or "-"
        lines.append(
            f"| {validation['dungeon']} | {validation['marker_count']} | "
            f"{validation['severity_counts']['error']} | "
            f"{validation['severity_counts']['warning']} | "
            f"{validation['severity_counts']['info']} | {code_text} |"
        )
    lines.extend(["", "## Findings", ""])
    for record in records:
        validation = record["validation"]
        if not validation["findings"]:
            continue
        lines.append(f"### {validation['dungeon']}")
        lines.append("")
        for finding in validation["findings"]:
            markers = ", ".join(finding["marker_ids"][:6])
            if len(finding["marker_ids"]) > 6:
                markers += f" (+{len(finding['marker_ids']) - 6})"
            lines.append(
                f"- **{finding['severity'].upper()} {finding['code']}**: "
                f"{finding['message']}"
                + (f" Markers: `{markers}`." if markers else "")
                + (f" Suggested: {finding['suggested_fix']}" if finding.get("suggested_fix") else "")
            )
        lines.append("")
    (root / "CURATION_VALIDATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    csv_path = root / "curation_validation.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "dungeon",
                "severity",
                "code",
                "message",
                "suggested_fix",
                "marker_ids",
                "coordinates",
            ],
        )
        writer.writeheader()
        for record in records:
            for finding in record["validation"]["findings"]:
                writer.writerow(
                    {
                        "dungeon": record["validation"]["dungeon"],
                        "severity": finding["severity"],
                        "code": finding["code"],
                        "message": finding["message"],
                        "suggested_fix": finding.get("suggested_fix", ""),
                        "marker_ids": ";".join(finding["marker_ids"]),
                        "coordinates": ";".join(finding["coordinates"]),
                    }
                )
    write_review_reports(root, records)


def compile_all(root: Path, selected: set[str] | None = None) -> list[dict]:
    records = []
    folders = sorted(path for path in root.iterdir() if path.is_dir())
    if selected:
        folders = [folder for folder in folders if folder.name in selected]
        missing = selected - {folder.name for folder in folders}
        if missing:
            raise ValueError("Unknown dungeon folder(s): " + ", ".join(sorted(missing)))
    for folder in folders:
        marker_path = folder / "curation_markers.json"
        if not marker_path.exists():
            continue
        compiled, validation = compile_dungeon(folder)
        output_dir = folder / "navigation"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "compiled_curation.json").write_text(
            json.dumps(compiled, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output_dir / "compiled_curation_map.txt").write_text(
            "\n".join(compiled["ascii_rows"]) + "\n",
            encoding="utf-8",
        )
        (output_dir / "curation_validation.json").write_text(
            json.dumps(validation, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        draw_validation_overlay(folder, validation, compiled).save(
            output_dir / "curation_validation_overlay.png"
        )
        records.append({"compiled": compiled, "validation": validation})
        print(
            f"{folder.name}: {validation['marker_count']} markers, "
            f"{validation['severity_counts']['error']} errors, "
            f"{validation['severity_counts']['warning']} warnings"
        )
    if not selected:
        write_global_reports(root, records)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile and validate all manual dungeon marker layers."
    )
    parser.add_argument("--root", default="emulator/maps/Dungeons")
    parser.add_argument("--dungeon", action="append")
    args = parser.parse_args()
    records = compile_all(Path(args.root), set(args.dungeon) if args.dungeon else None)
    totals = Counter()
    for record in records:
        totals.update(record["validation"]["severity_counts"])
    print(
        f"Compiled {len(records)} dungeon(s): "
        f"{totals.get('error', 0)} errors, {totals.get('warning', 0)} warnings, "
        f"{totals.get('info', 0)} info"
    )
    return 1 if totals.get("error", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
