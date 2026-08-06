"""Northeast_Tower specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class NortheastTower(BaseDungeon):
    """Northeast_Tower — puzzle logic not yet implemented."""

    map_id: int = 0  # TODO: assign actual map_id
    name: str = "Northeast_Tower"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Northeast_Tower map buffer formula not yet documented")
