"""Alunze_Northwest_Cave specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class AlunzeNorthwestCave(BaseDungeon):
    """Alunze_Northwest_Cave — puzzle logic not yet implemented."""

    map_id: int = 24
    name: str = "Alunze_Northwest_Cave"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Alunze_Northwest_Cave map buffer formula not yet documented")
