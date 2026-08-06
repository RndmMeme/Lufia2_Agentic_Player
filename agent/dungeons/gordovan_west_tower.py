"""Gordovan_West_Tower specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class GordovanWestTower(BaseDungeon):
    """Gordovan_West_Tower — puzzle logic not yet implemented."""

    map_id: int = 55
    name: str = "Gordovan_West_Tower"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Gordovan_West_Tower map buffer formula not yet documented")
