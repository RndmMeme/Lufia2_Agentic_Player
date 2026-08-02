"""Evidence-gated routing in the randomizer's 4000-unit overworld coordinate space."""

from __future__ import annotations

import json
from pathlib import Path

from agent.navigation.online_mapper import LiveNavigationObservation


WORLD_MAP_ID = 0
DIRECTIONS = {
    "north": (0, -1),
    "east": (1, 0),
    "west": (-1, 0),
    "south": (0, 1),
}


class OverworldNavigator:
    SCHEMA = "lufia2-overworld-navigation-v1"

    def __init__(self, path: Path, map_size: int = 4000, required_matches: int = 2):
        self.path = path
        self.map_size = int(map_size)
        self.required_matches = max(2, int(required_matches))
        self.state = {
            "schema": self.SCHEMA,
            "coordinate_source": "candidate WRAM 146B/146E walk or 1488/148B ship",
            "coordinate_verified": False,
            "matching_transitions": 0,
            "contradictions": 0,
            "samples": [],
            "visited_locations": [],
        }
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if loaded.get("schema") != self.SCHEMA:
                raise ValueError("Unsupported overworld navigation state schema")
            self.state.update(loaded)

    @property
    def verified(self) -> bool:
        return bool(self.state.get("coordinate_verified"))

    @property
    def visited_locations(self) -> set[str]:
        return set(self.state.get("visited_locations", []))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _wrapped_delta(self, before: int | float, after: int | float) -> float:
        half = self.map_size / 2
        return (float(after) - float(before) + half) % self.map_size - half

    def record_move(
        self,
        before: LiveNavigationObservation,
        direction: str,
        after: LiveNavigationObservation,
    ) -> dict | None:
        if before.map_id != WORLD_MAP_ID or after.map_id != WORLD_MAP_ID:
            return None
        dx = self._wrapped_delta(before.overworld_x, after.overworld_x)
        dy = self._wrapped_delta(before.overworld_y, after.overworld_y)
        if dx == 0 and dy == 0:
            return {"status": "no_world_coordinate_change", "dx": dx, "dy": dy}
        expected_x, expected_y = DIRECTIONS[direction]
        matches = (
            (expected_x == 0 and dx == 0 and dy * expected_y > 0)
            or (expected_y == 0 and dy == 0 and dx * expected_x > 0)
        )
        sample = {
            "direction": direction,
            "before": [before.overworld_x, before.overworld_y],
            "after": [after.overworld_x, after.overworld_y],
            "delta": [dx, dy],
            "matches": matches,
            "transport_flag": after.transport_flag,
        }
        self.state["samples"] = (self.state.get("samples", []) + [sample])[-12:]
        if matches:
            self.state["matching_transitions"] = int(self.state.get("matching_transitions", 0)) + 1
            if self.state["matching_transitions"] >= self.required_matches:
                self.state["coordinate_verified"] = True
        else:
            self.state["matching_transitions"] = 0
            self.state["contradictions"] = int(self.state.get("contradictions", 0)) + 1
            if self.state["contradictions"] >= 2:
                self.state["coordinate_verified"] = False
        self.save()
        return {"status": "match" if matches else "contradiction", **sample}

    def delta_to(self, position: tuple[int, int], target: tuple[float, float]) -> tuple[float, float]:
        return (
            self._wrapped_delta(position[0], target[0]),
            self._wrapped_delta(position[1], target[1]),
        )

    def distance_to(self, position: tuple[int, int], target: tuple[float, float]) -> float:
        dx, dy = self.delta_to(position, target)
        return abs(dx) + abs(dy)

    def next_direction(
        self,
        position: tuple[int, int],
        target: tuple[float, float],
        unavailable: set[str] | None = None,
    ) -> str | None:
        if not self.verified:
            return None
        unavailable = unavailable or set()
        dx, dy = self.delta_to(position, target)
        candidates = []
        if dx:
            candidates.append((abs(dx), "east" if dx > 0 else "west"))
        if dy:
            candidates.append((abs(dy), "south" if dy > 0 else "north"))
        for _, direction in sorted(candidates, reverse=True):
            if direction not in unavailable:
                return direction
        return next((direction for direction in DIRECTIONS if direction not in unavailable), None)

    def mark_visited(self, name: str) -> None:
        visited = list(self.state.get("visited_locations", []))
        if name not in visited:
            visited.append(name)
            self.state["visited_locations"] = visited
            self.save()
