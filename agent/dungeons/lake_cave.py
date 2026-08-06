"""Lake_Cave specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class LakeCave(BaseDungeon):
    """Lake_Cave — puzzle logic not yet implemented."""

    map_id: int = 10
    name: str = "Lake_Cave"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Lake_Cave map buffer formula not yet documented")
