"""Ancient_Tower specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class AncientTower(BaseDungeon):
    """Ancient_Tower — puzzle logic not yet implemented."""

    map_id: int = 75
    name: str = "Ancient_Tower"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Ancient_Tower map buffer formula not yet documented")
