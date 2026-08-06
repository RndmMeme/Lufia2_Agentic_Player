"""Flower_Mountain specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class FlowerMountain(BaseDungeon):
    """Flower_Mountain — puzzle logic not yet implemented."""

    map_id: int = 126
    name: str = "Flower_Mountain"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Flower_Mountain map buffer formula not yet documented")
