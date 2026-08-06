"""Shrine_Of_Vengeance specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class ShrineOfVengeance(BaseDungeon):
    """Shrine_Of_Vengeance — puzzle logic not yet implemented."""

    map_id: int = 174
    name: str = "Shrine_Of_Vengeance"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Shrine_Of_Vengeance map buffer formula not yet documented")
