"""Ruby_Cave specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class RubyCave(BaseDungeon):
    """Ruby_Cave — puzzle logic not yet implemented."""

    map_id: int = 39
    name: str = "Ruby_Cave"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Ruby_Cave map buffer formula not yet documented")
