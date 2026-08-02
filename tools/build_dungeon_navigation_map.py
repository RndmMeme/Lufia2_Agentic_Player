#!/usr/bin/env python3
"""Build an annotatable tile/navigation map from a full dungeon screenshot.

The image supplies a visual prior, not authoritative collision data. Runtime
movement confirms or rejects edges later through the actor coordinates and the
blocked-direction byte.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SCHEMA = "lufia2-dungeon-navigation-map-v2"
DEFAULT_TILE_SIZE = 16
CHESS_COORDINATE_RE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")

OBJECT_RULES = {
    "actor": {
        "render_tiles": {"width": 2, "height": 4},
        "render_size_px": {"width": 32, "height": 64},
        "navigation_anchor": "feet",
        "collision_model": (
            "The visible sprite may overlap walls. Collision and WRAM position "
            "are evaluated at the feet, not across the 32x64 render rectangle."
        ),
    },
    "door": {
        "orientation": "north_south_only",
        "bidirectional": True,
        "entry_directions": ["north", "south"],
        "lateral_entry": False,
        "front_marker": "arrow_on_pedestal",
        "back_marker": "lighter_sprite_gap_in_wall",
        "pairing": (
            "Front and back are the two faces of the same local doorway; "
            "never pair a front with a remote doorway."
        ),
        "typical_render_tiles": {"width": 2, "height": 4},
        "navigation_anchor": "pedestal_arrow_or_matching_wall_gap",
    },
    "stairs": {
        "tile_size_px": {"width": 16, "height": 16},
        "entry_directions": ["north", "south", "west", "east"],
        "placement_blocks_adjacent_entry": False,
        "pairing": (
            "Every endpoint has exactly one matching endpoint. Both endpoints "
            "use the same L/R handedness; L never pairs with R."
        ),
        "handedness_values": ["L", "R", "unknown"],
    },
    "monster": {
        "occupancy": "dynamic_obstacle",
        "underlying_terrain": "separate_from_monster_occupancy",
        "default_resolution_actions": ["defeat", "stun", "lure_away"],
        "navigation_effect": (
            "An occupied cell may be conditional even when its underlying "
            "terrain is walkable. Mandatory blockers become traversable after "
            "the monster is defeated."
        ),
    },
    "npc": {
        "occupancy": "dynamic_obstacle",
        "underlying_terrain": "separate_from_npc_occupancy",
        "default_resolution_actions": ["talk", "move_around", "wait"],
    },
}


def column_label(x: int) -> str:
    """Zero-based tile X to spreadsheet/chess-like column label."""
    if x < 0:
        raise ValueError("x must be non-negative")
    result = ""
    value = x + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def chess_coordinate(x: int, y: int) -> str:
    """Zero-based runtime tile coordinates to a human label such as AC55."""
    if y < 0:
        raise ValueError("y must be non-negative")
    return f"{column_label(x)}{y + 1}"


def parse_chess_coordinate(value: str) -> tuple[int, int]:
    """Human coordinate such as AC55 to a zero-based image tile position."""
    match = CHESS_COORDINATE_RE.fullmatch(value.upper())
    if not match:
        raise ValueError(f"Invalid chess coordinate: {value!r}")
    x = 0
    for character in match.group(1):
        x = x * 26 + ord(character) - ord("A") + 1
    return x - 1, int(match.group(2)) - 1


def parse_xy(value: str) -> tuple[int, int]:
    try:
        x_text, y_text = value.split(",", 1)
        x, y = int(x_text, 0), int(y_text, 0)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(
            f"Expected zero-based X,Y, got {value!r}"
        ) from exc
    if x < 0 or y < 0:
        raise argparse.ArgumentTypeError("X and Y must be non-negative")
    return x, y


def load_font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def pixel_features(tile: Image.Image, black_threshold: int) -> dict[str, float]:
    rgb_tile = tile.convert("RGB")
    pixels = list(rgb_tile.getdata())
    count = max(1, len(pixels))
    content = 0
    floor_like = 0
    green = 0

    for r, g, b in pixels:
        if max(r, g, b) > black_threshold:
            content += 1

        # Dirt, wood and red carpet are the dominant traversable surfaces in
        # Lufia II dungeon maps. This is deliberately only a visual prior.
        brown_or_red = (
            r >= 24
            and r >= g * 1.08
            and g >= b * 0.72
            and r - b >= 7
        )
        muted_floor = r >= 30 and 16 <= g <= r and 10 <= b <= g * 1.15
        if brown_or_red or muted_floor:
            floor_like += 1
        if g >= 24 and g > r * 1.10 and g > b * 1.12:
            green += 1

    inset_x = max(1, tile.width // 4)
    inset_y = max(1, tile.height // 4)
    center_pixels = list(
        rgb_tile.crop(
            (inset_x, inset_y, tile.width - inset_x, tile.height - inset_y)
        ).getdata()
    )
    center_content = sum(
        1 for r, g, b in center_pixels if max(r, g, b) > black_threshold
    )
    return {
        "content_ratio": round(content / count, 4),
        "center_content_ratio": round(
            center_content / max(1, len(center_pixels)),
            4,
        ),
        "floor_ratio": round(floor_like / count, 4),
        "green_ratio": round(green / count, 4),
    }


def visual_state(features: dict[str, float]) -> tuple[str, float]:
    content = features["content_ratio"]
    floor = features["floor_ratio"]
    if content < 0.08:
        return "void", round(1.0 - content, 4)
    # User-confirmed invariant for these dungeon map sheets: black borders are
    # walls. A mostly black tile center is therefore a hard visual blocker.
    if features["center_content_ratio"] < 0.35:
        return "black_wall", 1.0
    # Stay conservative: wall faces can contain brown pixels as well. Only a
    # tile dominated by floor-colored pixels becomes a planning prior.
    if floor >= 0.70:
        confidence = min(0.95, 0.35 + floor * 0.80)
        return "likely_walkable", round(confidence, 4)
    return "unknown", round(max(0.15, content * 0.5), 4)


def load_annotations(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    annotations = payload.get("annotations", payload)
    if not isinstance(annotations, dict):
        raise ValueError("annotations must be an object keyed by chess coordinate")
    return annotations


def _annotation_components(
    annotations: dict[str, dict],
    object_type: str,
) -> list[list[str]]:
    """Group horizontally contiguous visual fragments of one object."""
    matching = {
        coordinate
        for coordinate, annotation in annotations.items()
        if (annotation.get("object") or "").strip().lower() == object_type
    }
    components = []
    while matching:
        seed = matching.pop()
        component = [seed]
        pending = [seed]
        while pending:
            coordinate = pending.pop()
            x, y = parse_chess_coordinate(coordinate)
            for neighbor in (
                chess_coordinate(x - 1, y) if x > 0 else None,
                chess_coordinate(x + 1, y),
            ):
                if neighbor in matching:
                    matching.remove(neighbor)
                    component.append(neighbor)
                    pending.append(neighbor)
        components.append(
            sorted(component, key=lambda item: parse_chess_coordinate(item))
        )
    return sorted(
        components,
        key=lambda group: parse_chess_coordinate(group[0]),
    )


def _combined_annotation(
    annotations: dict[str, dict],
    coordinates: list[str],
) -> dict:
    values = [annotations[coordinate] for coordinate in coordinates]
    traversal_values = {value.get("traversal") for value in values}
    traversal = (
        "blocked"
        if "blocked" in traversal_values
        else "conditional"
        if "conditional" in traversal_values
        else "confirmed_walkable"
        if "confirmed_walkable" in traversal_values
        else next(iter(traversal_values), "unknown")
    )
    return {
        "traversal": traversal,
        "required_action": next(
            (
                value.get("required_action")
                for value in values
                if value.get("required_action")
            ),
            None,
        ),
        "notes": next(
            (value.get("notes") for value in values if value.get("notes")),
            None,
        ),
    }


def _stair_destination(annotation: dict) -> str | None:
    text = " ".join(
        value
        for value in (
            annotation.get("required_action"),
            annotation.get("notes"),
        )
        if value
    )
    match = re.search(
        r"\b(?:to|lead(?:s)?\s+to|takes?\s+(?:the\s+)?player\s+to|"
        r"sends?\s+(?:you\s+)?to)\s+([A-Z]+[1-9][0-9]*)\b",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1).upper() if match else None


def build_semantic_objects(annotations: dict[str, dict]) -> list[dict]:
    """Turn cell annotations into objects without treating pixels as collision."""
    objects = []

    for index, coordinates in enumerate(
        _annotation_components(annotations, "door"),
        start=1,
    ):
        combined = _combined_annotation(annotations, coordinates)
        objects.append(
            {
                "id": f"door-{index:03d}",
                "type": "door",
                "visual_cells": coordinates,
                "anchor_source": "curated_visual_cells",
                "orientation": "north_south",
                "bidirectional": True,
                "entry_directions": ["north", "south"],
                "front_back_relationship": "same_local_passage",
                **combined,
            }
        )

    stair_coordinates = sorted(
        (
            coordinate
            for coordinate, annotation in annotations.items()
            if (annotation.get("object") or "").strip().lower() == "stairs"
        ),
        key=parse_chess_coordinate,
    )
    stair_coordinate_set = set(stair_coordinates)
    stair_objects = []
    for index, coordinate in enumerate(
        stair_coordinates,
        start=1,
    ):
        annotation = annotations[coordinate]
        destination = _stair_destination(annotation)
        stair_objects.append(
            {
                "id": f"stairs-{index:03d}",
                "type": "stairs",
                "anchor": coordinate,
                "source": "curated",
                "tile_size_px": {"width": 16, "height": 16},
                "entry_directions": ["north", "south", "west", "east"],
                "placement_blocks_adjacent_entry": False,
                "handedness": annotation.get("handedness", "unknown"),
                "paired_with": destination,
                "pair_status": (
                    "reciprocal_annotation"
                    if destination in stair_coordinate_set
                    and _stair_destination(annotations[destination]) == coordinate
                    else "declared_target"
                    if destination
                    else "unresolved"
                ),
                "traversal": annotation.get("traversal"),
                "required_action": annotation.get("required_action"),
                "notes": annotation.get("notes"),
            }
        )

    # A declared stair destination is itself an endpoint even if the curator
    # only annotated the source. Keep it unverified rather than inventing a
    # collision state, but render it so it can be checked offline.
    derived_targets = {}
    for stair in stair_objects:
        destination = stair["paired_with"]
        if destination and destination not in stair_coordinate_set:
            derived_targets.setdefault(destination, stair["anchor"])
    for destination, source in sorted(
        derived_targets.items(),
        key=lambda item: parse_chess_coordinate(item[0]),
    ):
        stair_objects.append(
            {
                "id": f"stairs-{len(stair_objects) + 1:03d}",
                "type": "stairs",
                "anchor": destination,
                "source": "derived_from_pair",
                "tile_size_px": {"width": 16, "height": 16},
                "entry_directions": ["north", "south", "west", "east"],
                "placement_blocks_adjacent_entry": False,
                "handedness": "unknown",
                "handedness_inherited_from": source,
                "paired_with": source,
                "pair_status": "derived_reverse_endpoint",
                "traversal": "unverified",
                "required_action": None,
                "notes": f"Derived reverse endpoint of curated stair {source}.",
            }
        )

    objects.extend(stair_objects)
    return objects


def _stair_slope(
    source: Image.Image,
    coordinate: str,
    tile_size: int,
) -> tuple[int, float | None]:
    """Estimate the slash direction of the palette-invariant stair highlights."""
    x, y = parse_chess_coordinate(coordinate)
    tile = source.crop(
        (
            x * tile_size,
            y * tile_size,
            (x + 1) * tile_size,
            (y + 1) * tile_size,
        )
    ).convert("RGB")
    points = []
    for py in range(tile.height):
        for px in range(tile.width):
            red, green, blue = tile.getpixel((px, py))
            # The stair highlights are neutral/purple across the known cave
            # palettes. Ratios avoid binding the rule to one exact RGB value.
            if (
                blue > red * 1.15
                and blue > green * 1.05
                and blue > 45
            ):
                points.append((px, py))
    if len(points) < 4:
        return len(points), None
    mean_x = sum(px for px, _ in points) / len(points)
    mean_y = sum(py for _, py in points) / len(points)
    variance_x = sum((px - mean_x) ** 2 for px, _ in points)
    if variance_x <= 0.001:
        return len(points), None
    covariance = sum(
        (px - mean_x) * (py - mean_y)
        for px, py in points
    )
    return len(points), covariance / variance_x


def assign_stair_handedness(
    semantic_objects: list[dict],
    source: Image.Image,
    tile_size: int,
) -> None:
    """Assign one L/R variant to both endpoints of every known stair pair."""
    stairs = {
        semantic["anchor"]: semantic
        for semantic in semantic_objects
        if semantic["type"] == "stairs"
    }
    handled_pairs = set()
    for anchor, stair in stairs.items():
        destination = stair.get("paired_with")
        if destination not in stairs:
            continue
        pair_key = tuple(sorted((anchor, destination)))
        if pair_key in handled_pairs:
            continue
        handled_pairs.add(pair_key)
        candidates = []
        for coordinate in pair_key:
            sample_count, slope = _stair_slope(
                source,
                coordinate,
                tile_size,
            )
            if slope is not None and abs(slope) >= 0.15:
                candidates.append((sample_count, coordinate, slope))
        if not candidates:
            continue
        # The diagonal/open endpoint contains fewer highlight pixels than the
        # framed endpoint and exposes the L/R slash most clearly.
        sample_count, evidence_coordinate, slope = min(candidates)
        handedness = "L" if slope < 0 else "R"
        for coordinate in pair_key:
            stairs[coordinate]["handedness"] = handedness
            stairs[coordinate]["handedness_source"] = {
                "method": "stair_highlight_slope",
                "evidence_coordinate": evidence_coordinate,
                "sample_count": sample_count,
                "slope": round(slope, 4),
            }
            stairs[coordinate]["pair_handedness_valid"] = True


def object_symbol(object_type: str | None) -> str:
    return {
        "door": "D",
        "stairs": "T",
        "ladder": "H",
        "bush": "b",
        "chest": "C",
        "monster": "M",
        "npc": "N",
        "lever": "L",
        "floor switch": "s",
        "tile switch": "s",
        "puzzle": "P",
        "bridge": "=",
        "jump": "J",
    }.get((object_type or "").strip().lower(), " ")


def build_map(
    source_path: Path,
    tile_size: int = DEFAULT_TILE_SIZE,
    black_threshold: int = 8,
    annotations: dict[str, dict] | None = None,
    runtime_alignment: str = "unverified",
) -> tuple[dict, Image.Image]:
    source = Image.open(source_path).convert("RGB")
    width_tiles = (source.width + tile_size - 1) // tile_size
    height_tiles = (source.height + tile_size - 1) // tile_size
    padded = Image.new(
        "RGB",
        (width_tiles * tile_size, height_tiles * tile_size),
        (0, 0, 0),
    )
    padded.paste(source, (0, 0))
    annotations = annotations or {}
    semantic_objects = build_semantic_objects(annotations)
    assign_stair_handedness(semantic_objects, source, tile_size)
    derived_objects_by_cell = {
        semantic["anchor"]: semantic
        for semantic in semantic_objects
        if semantic["type"] == "stairs"
        and semantic.get("source") == "derived_from_pair"
    }

    cells = []
    rows = []
    object_rows = []
    counts = {
        "void": 0,
        "black_wall": 0,
        "likely_walkable": 0,
        "unknown": 0,
    }
    symbol_for = {
        "void": "#",
        "black_wall": "#",
        "likely_walkable": ".",
        "unknown": "?",
    }

    for y in range(height_tiles):
        symbols = []
        object_symbols = []
        for x in range(width_tiles):
            coordinate = chess_coordinate(x, y)
            tile = padded.crop(
                (
                    x * tile_size,
                    y * tile_size,
                    (x + 1) * tile_size,
                    (y + 1) * tile_size,
                )
            )
            features = pixel_features(tile, black_threshold)
            state, confidence = visual_state(features)
            counts[state] += 1
            annotation = annotations.get(coordinate, {})
            traversal = annotation.get(
                "traversal",
                (
                    "blocked"
                    if state in ("void", "black_wall")
                    else "unverified"
                ),
            )
            derived_object = derived_objects_by_cell.get(coordinate)
            object_type = annotation.get("object") or (
                derived_object["type"] if derived_object else None
            )
            if derived_object and not annotation:
                traversal = "unverified"
            symbol = {
                "blocked": "#",
                "confirmed_walkable": "o",
                "unverified": symbol_for[state],
                "unknown": "?",
                "conditional": (
                    "S"
                    if object_type == "secret_passage"
                    else "B" if object_type == "bombable_wall" else "!"
                ),
            }.get(traversal, symbol_for[state])
            symbols.append(symbol)
            object_symbols.append(object_symbol(object_type))
            cells.append(
                {
                    "x": x,
                    "y": y,
                    "coordinate": coordinate,
                    "visual_state": state,
                    "visual_confidence": confidence,
                    "traversal": traversal,
                    "object": object_type,
                    "required_action": annotation.get("required_action"),
                    "notes": annotation.get("notes"),
                    "object_source": (
                        "curated"
                        if annotation.get("object")
                        else "derived_from_pair"
                        if derived_object
                        else None
                    ),
                    **features,
                }
            )
        rows.append("".join(symbols))
        object_rows.append("".join(object_symbols))

    payload = {
        "schema": SCHEMA,
        "source_image": str(source_path),
        "grid": {
            "tile_size_px": tile_size,
            "width": width_tiles,
            "height": height_tiles,
            "source_width_px": source.width,
            "source_height_px": source.height,
            "padded_width_px": padded.width,
            "padded_height_px": padded.height,
        },
        "coordinates": {
            "space": "zero-based image tile grid",
            "runtime_alignment": runtime_alignment,
            "x": "image tile X; A=0, B=1, ..., Z=25, AA=26",
            "y": "image tile Y; displayed row is y+1",
            "registered_example": {
                "wram_x": 28,
                "wram_y": 54,
                "human": chess_coordinate(28, 54),
            } if runtime_alignment == "direct" else None,
        },
        "runtime": {
            "current_map": "7E:05AC uint8",
            "previous_map": "7E:05AE uint8",
            "actor_tile_x": "7E:06BA + actor slot",
            "actor_tile_y": "7E:06E2 + actor slot",
            "blocked_direction": "7E:1272: FF clear, 00 north, 01 south, 02 west, 03 east",
        },
        "navigation_policy": {
            "void": "blocked from the image prior",
            "black_wall": "always blocked; user-confirmed dungeon-map invariant",
            "likely_walkable": "may be planned through, but remains unverified",
            "unknown": "high-cost exploration only",
            "confirmed_walkable": "runtime movement succeeded",
            "collision_learning": (
                "On 7E:1272 != FF with unchanged actor X/Y, mark the attempted "
                "edge blocked and replan."
            ),
            "conditional_edges": (
                "secret_passage and bombable_wall annotations override the "
                "default wall only after the required interaction and a "
                "successful runtime movement confirm the edge."
            ),
            "render_vs_collision": (
                "The 16x16 grid is a feet-anchor/navigation lattice. Visible "
                "sprites and doors may overlap several cells without making "
                "those cells blocked."
            ),
        },
        "object_rules": OBJECT_RULES,
        "semantic_objects": semantic_objects,
        "visual_counts": counts,
        "legend": {
            "#": "blocked/void",
            ".": "visually likely walkable, unverified",
            "?": "unknown visual tile",
            "o": "runtime-confirmed walkable",
            "S": "annotated secret passage, conditional",
            "B": "annotated bombable wall, conditional",
            "!": "other conditional tile",
        },
        "rows": rows,
        "object_rows": object_rows,
        "cells": cells,
    }
    return payload, padded


def draw_coordinate_grid(
    source: Image.Image,
    payload: dict,
    scale: int = 2,
) -> Image.Image:
    tile_size = payload["grid"]["tile_size_px"]
    width_tiles = payload["grid"]["width"]
    height_tiles = payload["grid"]["height"]
    margin_left = 52
    margin_top = 30
    scaled_tile = tile_size * scale
    canvas = Image.new(
        "RGB",
        (
            margin_left + width_tiles * scaled_tile + 1,
            margin_top + height_tiles * scaled_tile + 1,
        ),
        (15, 15, 18),
    )
    scaled = source.resize(
        (source.width * scale, source.height * scale),
        Image.Resampling.NEAREST,
    )
    canvas.paste(scaled, (margin_left, margin_top))
    draw = ImageDraw.Draw(canvas)
    cell_font = load_font(max(8, 5 * scale))
    axis_font = load_font(max(10, 6 * scale))

    for x in range(width_tiles + 1):
        px = margin_left + x * scaled_tile
        draw.line(
            (px, margin_top, px, margin_top + height_tiles * scaled_tile),
            fill=(60, 210, 255),
            width=1,
        )
    for y in range(height_tiles + 1):
        py = margin_top + y * scaled_tile
        draw.line(
            (margin_left, py, margin_left + width_tiles * scaled_tile, py),
            fill=(60, 210, 255),
            width=1,
        )

    for x in range(width_tiles):
        label = column_label(x)
        px = margin_left + x * scaled_tile + 2
        draw.text((px, 5), label, font=axis_font, fill=(180, 235, 255))
    for y in range(height_tiles):
        label = str(y + 1)
        py = margin_top + y * scaled_tile + 2
        draw.text((3, py), label, font=axis_font, fill=(180, 235, 255))
        for x in range(width_tiles):
            coordinate = chess_coordinate(x, y)
            px = margin_left + x * scaled_tile + 2
            draw.text(
                (px, py),
                coordinate,
                font=cell_font,
                fill=(235, 250, 255),
                stroke_width=1,
                stroke_fill=(0, 0, 0),
            )
    return canvas


def draw_navigation_preview(source: Image.Image, payload: dict, scale: int = 2):
    image = source.resize(
        (source.width * scale, source.height * scale),
        Image.Resampling.NEAREST,
    ).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    tile_size = payload["grid"]["tile_size_px"] * scale
    colors = {
        "void": (10, 10, 15, 155),
        "black_wall": (210, 30, 45, 120),
        "likely_walkable": (30, 220, 90, 62),
        "unknown": (255, 165, 20, 72),
    }
    for cell in payload["cells"]:
        x0 = cell["x"] * tile_size
        y0 = cell["y"] * tile_size
        draw.rectangle(
            (x0, y0, x0 + tile_size - 1, y0 + tile_size - 1),
            fill=colors[cell["visual_state"]],
        )

        if cell["object"]:
            curated_color = {
                "blocked": (255, 55, 70, 245),
                "conditional": (255, 215, 40, 245),
                "confirmed_walkable": (40, 255, 150, 245),
            }.get(cell["traversal"], (90, 210, 255, 235))
            draw.rectangle(
                (x0 + 1, y0 + 1, x0 + tile_size - 2, y0 + tile_size - 2),
                outline=curated_color,
                width=max(2, scale),
            )
            symbol = object_symbol(cell["object"])
            if symbol.strip():
                draw.text(
                    (x0 + 2 * scale, y0 + scale),
                    symbol,
                    font=load_font(max(9, 7 * scale)),
                    fill=(255, 255, 255, 255),
                    stroke_width=max(1, scale // 2),
                    stroke_fill=(0, 0, 0, 255),
                )

    # Object-level semantics are drawn independently from pixel occupancy.
    for semantic in payload.get("semantic_objects", []):
        if semantic["type"] == "door":
            points = [
                parse_chess_coordinate(coordinate)
                for coordinate in semantic["visual_cells"]
            ]
            min_x = min(x for x, _ in points) * tile_size
            max_x = (max(x for x, _ in points) + 1) * tile_size - 1
            min_y = min(y for _, y in points) * tile_size
            max_y = (max(y for _, y in points) + 1) * tile_size - 1
            center_x = (min_x + max_x) // 2
            draw.rectangle(
                (min_x, min_y, max_x, max_y),
                outline=(80, 225, 255, 255),
                width=max(2, scale),
            )
            draw.line(
                (
                    center_x,
                    min_y - tile_size // 3,
                    center_x,
                    max_y + tile_size // 3,
                ),
                fill=(80, 225, 255, 255),
                width=max(2, scale),
            )
        elif semantic["type"] == "stairs":
            x, y = parse_chess_coordinate(semantic["anchor"])
            x0 = x * tile_size
            y0 = y * tile_size
            center_x = x0 + tile_size // 2
            center_y = y0 + tile_size // 2
            arm = tile_size // 3
            draw.line(
                (center_x - arm, center_y, center_x + arm, center_y),
                fill=(120, 245, 255, 255),
                width=max(2, scale),
            )
            draw.line(
                (center_x, center_y - arm, center_x, center_y + arm),
                fill=(120, 245, 255, 255),
                width=max(2, scale),
            )
    return Image.alpha_composite(image, overlay)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a reusable Lufia II dungeon navigation grid."
    )
    parser.add_argument("source_image")
    parser.add_argument("--output-dir")
    parser.add_argument("--annotations")
    parser.add_argument("--tile-size", type=int, default=DEFAULT_TILE_SIZE)
    parser.add_argument("--black-threshold", type=int, default=8)
    parser.add_argument("--overlay-scale", type=int, default=2)
    parser.add_argument(
        "--runtime-alignment",
        choices=("unverified", "direct"),
        default="unverified",
    )
    args = parser.parse_args()

    source_path = Path(args.source_image)
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else source_path.parent / "navigation"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    annotation_path = Path(args.annotations) if args.annotations else None
    annotations = load_annotations(annotation_path)

    payload, padded = build_map(
        source_path,
        tile_size=args.tile_size,
        black_threshold=args.black_threshold,
        annotations=annotations,
        runtime_alignment=args.runtime_alignment,
    )
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

    print(f"Built {payload['grid']['width']}x{payload['grid']['height']} grid")
    print(f"Visual counts: {payload['visual_counts']}")
    print(f"Output: {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
