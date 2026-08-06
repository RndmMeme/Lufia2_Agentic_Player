"""Alunze_Castle_Basement specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class AlunzeCastleBasement(BaseDungeon):
    """Alunze_Castle_Basement — puzzle logic not yet implemented."""

    map_id: int = 15
    name: str = "Alunze_Castle_Basement"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Alunze_Castle_Basement map buffer formula not yet documented")
