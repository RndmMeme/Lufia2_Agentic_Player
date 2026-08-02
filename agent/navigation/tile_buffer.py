"""Compact, map-scoped WRAM tile-buffer sensing for Lufia II navigation."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRATIONS = ROOT / "data/navigation_semantics"


class TileBufferRegistry:
    """Decode only buffers with an explicitly confirmed per-map registration."""

    SYMBOLS = {
        0x00: ".", 0x01: "@", 0x02: "O", 0x03: "o",
        0x06: "L", 0x07: "l", 0x08: "X", 0x09: "x",
        0x10: "[", 0x11: "{", 0x20: ":", 0x21: "*",
        0x30: "]", 0x31: "}", 0xFF: " ",
    }

    def __init__(self, directory: Path = DEFAULT_REGISTRATIONS):
        self.registrations = {}
        if directory.exists():
            for path in directory.glob("*.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if "map_id" in payload and "buffer" in payload:
                    self.registrations[int(payload["map_id"])] = payload

    def registration(self, map_id: int) -> dict | None:
        return self.registrations.get(int(map_id))

    @staticmethod
    def _address(buffer: dict, x: int, y: int) -> int:
        return int(buffer["base"]) + int(x) + int(y) * int(buffer["stride"])

    @staticmethod
    def _family(registration: dict, value: int) -> dict:
        families = registration.get("tile_families", {})
        exact = families.get(f"{value:02X}")
        if exact:
            return {"value": value, **exact, "occupied": bool(value & 1)}
        base_value = value & 0xFE
        base = families.get(f"{base_value:02X}")
        if base:
            return {"value": value, **base, "occupied": bool(value & 1)}
        return {"value": value, "family": "unknown", "occupied": bool(value & 1)}

    def context(self, map_id: int, x: int, y: int, wram: bytes, radius: int = 2) -> dict:
        registration = self.registration(map_id)
        if registration is None:
            return {"available": False, "reason": "no_confirmed_map_buffer_registration"}
        buffer = registration["buffer"]
        width, height = int(buffer["width"]), int(buffer["height"])
        radius = max(1, min(int(radius), 4))
        rows = []
        cells = []
        for tile_y in range(y - radius, y + radius + 1):
            symbols = []
            for tile_x in range(x - radius, x + radius + 1):
                if not (0 <= tile_x < width and 0 <= tile_y < height):
                    symbols.append(" ")
                    continue
                address = self._address(buffer, tile_x, tile_y)
                if not 0 <= address < len(wram):
                    symbols.append("?")
                    continue
                value = wram[address]
                symbols.append("@" if (tile_x, tile_y) == (x, y) else self.SYMBOLS.get(value, "?"))
                if abs(tile_x - x) + abs(tile_y - y) <= 1:
                    cells.append({
                        "relative": [tile_x - x, tile_y - y],
                        "live": [tile_x, tile_y],
                        "address": f"0x{address:04X}",
                        **self._family(registration, value),
                    })
            rows.append("".join(symbols))
        return {
            "available": True,
            "scope": registration["scope"],
            "center_live": [x, y],
            "radius": radius,
            "rows": rows,
            "cardinal_cells": cells,
            "legend": "@ actor feet; . floor; O gap; L lever/switch; X obstacle; [/] structural; : alternate floor; ? unknown",
            "policy": (
                "This is map-scoped tile-family evidence. Combine it with blocked_now and room semantics; "
                "never infer universal walkability from a family value alone."
            ),
        }

    def diff(
        self,
        map_id: int,
        before: bytes,
        after: bytes,
        ignore_live_points: set[tuple[int, int]] | None = None,
        limit: int = 12,
    ) -> dict:
        registration = self.registration(map_id)
        if registration is None:
            return {"available": False, "count": 0, "changes": []}
        buffer = registration["buffer"]
        width, height = int(buffer["width"]), int(buffer["height"])
        ignored = ignore_live_points or set()
        changes = []
        total = 0
        semantic_total = 0
        occupancy_total = 0
        for tile_y in range(height):
            row_address = self._address(buffer, 0, tile_y)
            for tile_x in range(width):
                if (tile_x, tile_y) in ignored:
                    continue
                address = row_address + tile_x
                if address >= len(before) or address >= len(after):
                    continue
                if before[address] == after[address]:
                    continue
                total += 1
                before_family = self._family(registration, before[address])["family"]
                after_family = self._family(registration, after[address])["family"]
                semantic = before_family != after_family
                if semantic:
                    semantic_total += 1
                else:
                    occupancy_total += 1
                if len(changes) < max(0, int(limit)):
                    changes.append({
                        "live": [tile_x, tile_y],
                        "address": f"0x{address:04X}",
                        "before": f"{before[address]:02X}",
                        "after": f"{after[address]:02X}",
                        "before_family": before_family,
                        "after_family": after_family,
                        "semantic_family_change": semantic,
                    })
        return {
            "available": True,
            "scope": registration["scope"],
            "count": total,
            "semantic_count": semantic_total,
            "occupancy_count": occupancy_total,
            "changes": changes,
            "truncated": total > len(changes),
        }
