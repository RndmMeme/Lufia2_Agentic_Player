"""Cave_to_Sundletan specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class CavetoSundletan(BaseDungeon):
    """Cave_to_Sundletan — puzzle logic not yet implemented."""

    map_id: int = 6
    name: str = "Cave_to_Sundletan"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Cave_to_Sundletan map buffer formula not yet documented")
