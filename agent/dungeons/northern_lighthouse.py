"""Northern_Lighthouse specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class NorthernLighthouse(BaseDungeon):
    """Northern_Lighthouse — puzzle logic not yet implemented."""

    map_id: int = 0  # TODO: assign actual map_id
    name: str = "Northern_Lighthouse"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Northern_Lighthouse map buffer formula not yet documented")
