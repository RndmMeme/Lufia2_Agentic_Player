"""Dragon_Mountain specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class DragonMountain(BaseDungeon):
    """Dragon_Mountain — puzzle logic not yet implemented."""

    map_id: int = 192
    name: str = "Dragon_Mountain"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Dragon_Mountain map buffer formula not yet documented")
