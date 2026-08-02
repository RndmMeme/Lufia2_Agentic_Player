"""Zone hierarchy parsed from Abyssonym's authoritative zones.txt table."""

from __future__ import annotations

import re
from pathlib import Path


_ZONE_LINE = re.compile(
    r"^\s*([0-9A-Fa-f]{2}):([0-9A-Fa-f]{2}(?:,[0-9A-Fa-f]{2})*)\s+(.+?)\s*$"
)
_ZONES_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "terrorwave_reference"
    / "tables"
    / "zones.txt"
)


def _load_zones(path: Path = _ZONES_PATH):
    zones = {}
    map_to_zone = {}

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        match = _ZONE_LINE.match(raw_line)
        if not match:
            raise ValueError(f"Invalid zones.txt line {line_number}: {raw_line!r}")

        zone_id = int(match.group(1), 16)
        map_ids = tuple(int(value, 16) for value in match.group(2).split(","))
        name = match.group(3).strip()
        zones[zone_id] = {
            "id": zone_id,
            "id_hex": f"{zone_id:02X}",
            "name": name,
            "map_ids": map_ids,
        }

        for map_id in map_ids:
            if map_id in map_to_zone:
                previous = map_to_zone[map_id]
                raise ValueError(
                    f"Map {map_id:02X} belongs to both zones "
                    f"{previous:02X} and {zone_id:02X}"
                )
            map_to_zone[map_id] = zone_id

    return zones, map_to_zone


ZONE_DB, MAP_TO_ZONE = _load_zones()


def zone_for_map(map_id: int):
    """Return the authoritative parent-zone record for a runtime map ID."""
    zone_id = MAP_TO_ZONE.get(int(map_id))
    return ZONE_DB.get(zone_id) if zone_id is not None else None
