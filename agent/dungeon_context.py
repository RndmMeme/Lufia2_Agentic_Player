"""Conservative lookup of curated dungeon semantics for a live map position."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from emulator.zone_db import zone_for_map


ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "emulator/maps/Dungeons/navigation_index.json"


def normalized(value: str) -> str:
    value = re.sub(r"\b(b\d+|\d+f|north|south|east|west|northeast|northwest)\b", " ", value.casefold())
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


class DungeonContextRegistry:
    def __init__(self, index_path: Path = INDEX_PATH):
        self.records = json.loads(index_path.read_text(encoding="utf-8"))["records"]
        self._compiled_cache: dict[str, dict] = {}

    def _record_for_map(self, map_id: int) -> dict | None:
        zone = zone_for_map(map_id)
        if not zone:
            return None
        zone_name = normalized(zone["name"])
        scored = []
        for record in self.records:
            dungeon_name = normalized(record["dungeon"])
            score = SequenceMatcher(None, zone_name, dungeon_name).ratio()
            if zone_name in dungeon_name or dungeon_name in zone_name:
                score += 0.5
            scored.append((score, record))
        score, record = max(scored, key=lambda item: item[0])
        return record if score >= 0.55 else None

    @staticmethod
    def _marker_anchor(marker: dict) -> dict:
        """Accept the current compiler schema and older hand-written records."""
        return marker.get("anchor_cell") or marker.get("anchor") or {}

    def _compiled_for(self, record: dict) -> dict:
        source = str(record["source_image"])
        if source not in self._compiled_cache:
            dungeon_root = (ROOT / source).parent
            self._compiled_cache[source] = json.loads(
                (dungeon_root / "navigation/compiled_curation.json").read_text(encoding="utf-8")
            )
        return self._compiled_cache[source]

    def context(self, map_id: int, x: int, y: int, radius: int = 2) -> dict:
        record = self._record_for_map(map_id)
        if record is None:
            return {"registered": False, "reason": "no_dungeon_match"}
        nav_path = ROOT / record["source_image"]
        dungeon_root = nav_path.parent
        navigation = json.loads((dungeon_root / "navigation/navigation_map.json").read_text(encoding="utf-8"))
        alignment = navigation.get("coordinates", {}).get("runtime_alignment", record.get("runtime_alignment"))
        result = {
            "registered": True,
            "dungeon": record["dungeon"],
            "runtime_alignment": alignment,
            "coordinate_semantics_available": alignment == "direct",
            "source_image": record["source_image"],
        }
        if alignment != "direct":
            result["warning"] = "Do not project WRAM x/y onto this image until runtime registration is proven."
            return result
        compiled = self._compiled_for(record)
        nearby = []
        for marker in compiled.get("markers", []):
            anchor = self._marker_anchor(marker)
            if "x" not in anchor or "y" not in anchor:
                continue
            dx, dy = int(anchor["x"]) - x, int(anchor["y"]) - y
            if abs(dx) <= radius and abs(dy) <= radius:
                nearby.append(
                    {
                        "id": marker.get("id"),
                        "type": marker.get("type"),
                        "traversal": marker.get("traversal"),
                        "required_action": marker.get("required_action"),
                        "notes": marker.get("notes"),
                        "coordinate": anchor.get("coordinate"),
                        "dx": dx,
                        "dy": dy,
                    }
                )
        nearby.sort(key=lambda marker: (abs(marker["dx"]) + abs(marker["dy"]), marker["id"] or ""))
        result["nearby_markers"] = nearby

        nearby_cells = []
        for cell in compiled.get("cells", []):
            dx, dy = int(cell["x"]) - x, int(cell["y"]) - y
            if abs(dx) <= radius and abs(dy) <= radius:
                nearby_cells.append(
                    {
                        "coordinate": cell.get("coordinate"),
                        "traversal": cell.get("effective_traversal"),
                        "terrain": cell.get("terrain", []),
                        "objects": cell.get("objects", []),
                        "dx": dx,
                        "dy": dy,
                    }
                )
        nearby_cells.sort(
            key=lambda cell: (abs(cell["dx"]) + abs(cell["dy"]), cell["coordinate"] or "")
        )
        result["nearby_cells"] = nearby_cells
        return result

    def directional_priors(self, map_id: int, x: int, y: int, distance: int = 2) -> dict[str, str]:
        """Return soft curated hints; live WRAM movement remains authoritative."""
        record = self._record_for_map(map_id)
        if record is None or record.get("runtime_alignment") != "direct":
            return {}
        compiled = self._compiled_for(record)
        cells = {(int(cell["x"]), int(cell["y"])): cell for cell in compiled.get("cells", [])}
        vectors = {
            "north": (0, -1),
            "east": (1, 0),
            "west": (-1, 0),
            "south": (0, 1),
        }
        priors = {}
        for direction, (dx, dy) in vectors.items():
            evidence = [cells.get((x + dx * step, y + dy * step)) for step in range(1, distance + 1)]
            known = [cell for cell in evidence if cell is not None]
            traversals = {str(cell.get("effective_traversal", "unknown")) for cell in known}
            if "blocked" in traversals:
                priors[direction] = "blocked"
            elif "conditional" in traversals:
                priors[direction] = "conditional"
            elif len(known) == distance and traversals <= {"confirmed_walkable", "walkable"}:
                priors[direction] = "confirmed_walkable"
            elif known:
                priors[direction] = "partially_known"
            else:
                priors[direction] = "unknown"
        return priors

    def navigation_briefing(self, map_id: int, x: int, y: int, radius: int = 9) -> dict:
        """Return map evidence for the LLM without selecting a direction."""
        record = self._record_for_map(map_id)
        if record is None:
            return {"available": False, "reason": "no_dungeon_match"}
        dungeon_root = (ROOT / record["source_image"]).parent
        navigation = json.loads(
            (dungeon_root / "navigation/navigation_map.json").read_text(encoding="utf-8")
        )
        alignment = navigation.get("coordinates", {}).get(
            "runtime_alignment", record.get("runtime_alignment")
        )
        if alignment != "direct":
            return {
                "available": True,
                "dungeon": record["dungeon"],
                "coordinate_semantics_available": False,
                "runtime_alignment": alignment,
                "ascii_crop": None,
                "nearby_curated_markers": [],
                "full_map_image": str(
                    (dungeon_root / "navigation/navigation_preview.png").resolve()
                ),
                "warning": (
                    "The stitched image is visual reference only. Never place WRAM x/y "
                    "directly on its grid; use the active room's live landmarks."
                ),
                "policy": (
                    "The LLM may compare the live frame with the full map visually, but "
                    "room topology and WRAM outcomes are authoritative."
                ),
            }
        rows = list(navigation.get("rows", []))
        if not rows:
            return {"available": False, "reason": "no_ascii_rows"}
        min_y = max(0, y - radius)
        max_y = min(len(rows) - 1, y + radius)
        min_x = max(0, x - radius)
        max_x = min(len(rows[0]) - 1, x + radius)
        crop = []
        for row_y in range(min_y, max_y + 1):
            chars = list(rows[row_y][min_x : max_x + 1])
            if row_y == y and min_x <= x <= max_x:
                chars[x - min_x] = "@"
            crop.append(f"{row_y:02d} " + "".join(chars))
        compiled = self._compiled_for(record)
        markers = []
        for marker in compiled.get("markers", []):
            anchor = self._marker_anchor(marker)
            if "x" not in anchor or "y" not in anchor:
                continue
            dx, dy = int(anchor["x"]) - x, int(anchor["y"]) - y
            if abs(dx) <= radius and abs(dy) <= radius:
                markers.append({
                    "type": marker.get("type"),
                    "coordinate": anchor.get("coordinate"),
                    "relative": [dx, dy],
                    "traversal": marker.get("traversal"),
                    "required_action": marker.get("required_action"),
                    "notes": marker.get("notes"),
                })
        markers.sort(key=lambda item: abs(item["relative"][0]) + abs(item["relative"][1]))
        return {
            "available": True,
            "dungeon": record["dungeon"],
            "coordinate_bounds": {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y},
            "ascii_crop": "\n".join(crop),
            "legend": "@ player feet; # blocked; . likely walkable; o confirmed walkable; ! conditional; ? visually uncertain",
            "nearby_curated_markers": markers[:16],
            "full_map_image": str((dungeon_root / "navigation/navigation_preview.png").resolve()),
            "policy": "Evidence only. The map never selects or executes a direction; the LLM must decide.",
        }
