"""Tanbel_Southeast_Tower specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class TanbelSoutheastTower(BaseDungeon):
    """Tanbel_Southeast_Tower — puzzle logic not yet implemented."""

    map_id: int = 30
    name: str = "Tanbel_Southeast_Tower"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Tanbel_Southeast_Tower map buffer formula not yet documented")
