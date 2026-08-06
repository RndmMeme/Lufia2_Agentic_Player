"""Mountain_Of_No_Return specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class MountainOfNoReturn(BaseDungeon):
    """Mountain_Of_No_Return — puzzle logic not yet implemented."""

    map_id: int = 163
    name: str = "Mountain_Of_No_Return"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Mountain_Of_No_Return map buffer formula not yet documented")
