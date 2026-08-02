"""Randomizer access-logic evaluation and bounded strategic goal ranking."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


ALIASES = {
    "fire arrow": "fire",
    "mermaid jade": "jade",
    "basement key": "basement",
    "dankirk key": "dankirk",
    "flower key": "flower",
    "ghost key": "ghost",
    "heart key": "heart",
    "lake key": "lake",
    "light key": "light",
    "magma key": "magma",
    "narcysus key": "narcysus",
    "ruby key": "ruby",
    "sky key": "sky",
    "sword key": "sword",
    "tree key": "tree",
    "trial key": "trial",
    "truth key": "truth",
    "wind key": "wind",
}


def normalize_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    return ALIASES.get(token, token)


@dataclass(frozen=True)
class LocationAccess:
    name: str
    accessible: bool
    satisfied_rule: tuple[str, ...] | None
    closest_missing: tuple[str, ...]
    world_position: tuple[float, float] | None


class ProgressionPlanner:
    def __init__(
        self,
        logic_path: Path = ROOT / "data/locations_logic.json",
        locations_path: Path = ROOT / "data/locations.json",
    ):
        self.logic = json.loads(logic_path.read_text(encoding="utf-8"))
        self.locations = json.loads(locations_path.read_text(encoding="utf-8"))

    @staticmethod
    def _rules(record: dict) -> list[tuple[str, ...]]:
        raw_rules = record.get("access_rules", [])
        if not raw_rules:
            return [tuple()]
        return [
            tuple(normalize_token(part) for part in rule.split(",") if part.strip())
            for rule in raw_rules
        ]

    def evaluate(self, owned_items: list[str] | tuple[str, ...]) -> list[LocationAccess]:
        owned = {normalize_token(item) for item in owned_items}
        results = []
        for name, record in self.logic.items():
            rules = self._rules(record)
            satisfied = next((rule for rule in rules if set(rule) <= owned), None)
            missing_sets = [tuple(item for item in rule if item not in owned) for rule in rules]
            closest = min(missing_sets, key=lambda values: (len(values), values)) if missing_sets else tuple()
            position = self.locations.get(name)
            results.append(
                LocationAccess(
                    name=name,
                    accessible=satisfied is not None,
                    satisfied_rule=satisfied,
                    closest_missing=closest,
                    world_position=tuple(position) if position else None,
                )
            )
        return results

    def choose_goal(
        self,
        owned_items: list[str] | tuple[str, ...],
        visited: set[str] | None = None,
        current_world_position: tuple[float, float] | None = None,
    ) -> dict:
        visited = visited or set()
        evaluated = self.evaluate(owned_items)
        final = next((item for item in evaluated if item.name == "Daos' Shrine"), None)
        if final and final.accessible and final.name not in visited:
            chosen = final
            reason = "final_location_accessible"
        else:
            candidates = [item for item in evaluated if item.accessible and item.name not in visited]
            if current_world_position is not None:
                def distance(item):
                    if item.world_position is None:
                        return float("inf")
                    return abs(item.world_position[0] - current_world_position[0]) + abs(
                        item.world_position[1] - current_world_position[1]
                    )
                candidates.sort(key=lambda item: (distance(item), item.name))
                reason = "nearest_accessible_unvisited"
            else:
                candidates.sort(key=lambda item: item.name)
                reason = "accessible_unvisited"
            chosen = candidates[0] if candidates else None
        return {
            "goal": chosen.name if chosen else None,
            "reason": reason if chosen else "no_accessible_unvisited_location",
            "world_position": chosen.world_position if chosen else None,
            "satisfied_rule": chosen.satisfied_rule if chosen else None,
            "accessible": sorted(item.name for item in evaluated if item.accessible),
            "blocked_nearest_requirements": {
                item.name: item.closest_missing
                for item in evaluated
                if not item.accessible and len(item.closest_missing) <= 2
            },
        }
