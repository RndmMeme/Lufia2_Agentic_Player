"""Base interface for dungeon-specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any


class BaseDungeon:
    """Base class for dungeon-specific feedback and puzzle logic."""

    map_id: int = 0
    name: str = ""

    def __init__(self, controller: Any) -> None:
        self.controller = controller

    def on_use_tool(self, before: Any, after: Any) -> str | None:
        """Return a feedback message after a use_tool action, or None."""
        return None

    def on_reset_room(self, before: Any, after: Any) -> str | None:
        """Return a feedback message after a reset_room action, or None."""
        return None

    def on_move(self, before: Any, after: Any, direction: str, tiles: int) -> str | None:
        """Return a feedback message after a move action, or None."""
        return None

    def navigation_target(
        self, observation: Any, mapper: Any, room_context: dict
    ) -> dict | None:
        """Select a state-aware active landmark, if this dungeon defines one."""
        return None

    def established_memory(
        self, observation: Any, room_context: dict
    ) -> list[dict]:
        """Return curated run-independent facts for the currently classified room."""
        return []

    def provisional_object_target(
        self, observation: Any, room_context: dict, candidates: dict
    ) -> dict | None:
        """Correlate a live dynamic-cell candidate with established dungeon state."""
        return None

    def tile_address(self, x: int, y: int) -> int:
        """Return the WRAM address for a live tile coordinate."""
        raise NotImplementedError

    def read_tile(self, x: int, y: int) -> int:
        """Read a tile value from live WRAM."""
        addr = self.tile_address(x, y)
        wram = self.controller.bridge.read(addr, 1)
        return wram[0] if wram else 0xFF
