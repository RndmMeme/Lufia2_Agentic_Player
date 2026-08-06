"""Gratze_Castle specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class GratzeCastle(BaseDungeon):
    """Gratze_Castle — puzzle logic not yet implemented."""

    map_id: int = 209
    name: str = "Gratze_Castle"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Gratze_Castle map buffer formula not yet documented")
