"""Karlloon_North_Shrine specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class KarlloonNorthShrine(BaseDungeon):
    """Karlloon_North_Shrine — puzzle logic not yet implemented."""

    map_id: int = 117
    name: str = "Karlloon_North_Shrine"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Karlloon_North_Shrine map buffer formula not yet documented")
