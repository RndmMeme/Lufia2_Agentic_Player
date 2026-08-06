"""Kamirno_Tower specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class KamirnoTower(BaseDungeon):
    """Kamirno_Tower — puzzle logic not yet implemented."""

    map_id: int = 226
    name: str = "Kamirno_Tower"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Kamirno_Tower map buffer formula not yet documented")
