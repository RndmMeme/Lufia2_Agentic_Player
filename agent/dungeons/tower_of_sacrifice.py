"""Tower_Of_Sacrifice specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class TowerOfSacrifice(BaseDungeon):
    """Tower_Of_Sacrifice — puzzle logic not yet implemented."""

    map_id: int = 108
    name: str = "Tower_Of_Sacrifice"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Tower_Of_Sacrifice map buffer formula not yet documented")
