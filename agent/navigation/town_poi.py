"""Parser for the existing human-maintained town_POI_coords.txt table."""

from __future__ import annotations

import re
from pathlib import Path


HEADER_RE = re.compile(r"^Town\s+map_id\s+Building", re.IGNORECASE)
MAP_ROW_RE = re.compile(r"^\s*(.*?)\s+([0-9A-Fa-f]{1,2})\s{2,}(.+?)\s{2,}(ext|int)\s*(.*?)\s*$")
CONTINUATION_RE = re.compile(r"^\s*(.+?)\s{2,}(ext|int)\s*(.*?)\s*$")
COORD_RE = re.compile(r"^\s*(-?\d+)\s*,\s*(-?\d+)")
WRAPPED_X_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*,\s*(-?\d+)")


def _coordinates(text: str) -> tuple[tuple[int, int] | None, list[int] | None]:
    wrapped = WRAPPED_X_RE.search(text or "")
    if wrapped:
        return (int(wrapped.group(1)), int(wrapped.group(3))), [
            int(wrapped.group(1)),
            int(wrapped.group(2)),
        ]
    match = COORD_RE.search(text or "")
    return ((int(match.group(1)), int(match.group(2))), None) if match else (None, None)


def load_town_pois(path: Path | str = "data/town_POI_coords.txt") -> list[dict]:
    entries = []
    current_town = None
    current_map_id = None
    for raw_line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.replace("\t", "    ").rstrip()
        if not line.strip() or HEADER_RE.search(line):
            continue
        map_match = MAP_ROW_RE.match(line)
        if map_match:
            current_town = map_match.group(1).strip()
            current_map_id = int(map_match.group(2), 16)
            label = map_match.group(3).strip()
            area = map_match.group(4).lower()
            coordinate_text = map_match.group(5)
        else:
            continuation = CONTINUATION_RE.match(line)
            if not continuation or current_map_id is None:
                continue
            label = continuation.group(1).strip()
            area = continuation.group(2).lower()
            coordinate_text = continuation.group(3)
        coords, wrapped_x = _coordinates(coordinate_text)
        entries.append(
            {
                "town": current_town,
                "map_id": current_map_id,
                "label": label,
                "area": "exterior" if area == "ext" else "interior",
                "x": coords[0] if coords else None,
                "y": coords[1] if coords else None,
                "wrapped_x_range": wrapped_x,
                "raw_coordinates": coordinate_text.strip(),
            }
        )
    return entries


def pois_for_map(entries: list[dict], map_id: int) -> list[dict]:
    return [entry for entry in entries if int(entry["map_id"]) == int(map_id)]
