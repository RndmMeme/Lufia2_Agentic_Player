"""Tower_Of_Truth specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class TowerOfTruth(BaseDungeon):
    """Tower_Of_Truth — puzzle logic not yet implemented."""

    map_id: int = 183
    name: str = "Tower_Of_Truth"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Tower_Of_Truth map buffer formula not yet documented")
