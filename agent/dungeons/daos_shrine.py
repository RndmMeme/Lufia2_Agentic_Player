"""Daos' Shrine specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class DaosShrine(BaseDungeon):
    """Daos' Shrine — puzzle logic not yet implemented."""

    map_id: int = 230
    name: str = "Daos' Shrine"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Daos' Shrine map buffer formula not yet documented")
