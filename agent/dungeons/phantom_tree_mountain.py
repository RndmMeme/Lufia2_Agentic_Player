"""Phantom_Tree_Mountain specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class PhantomTreeMountain(BaseDungeon):
    """Phantom_Tree_Mountain — puzzle logic not yet implemented."""

    map_id: int = 96
    name: str = "Phantom_Tree_Mountain"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("Phantom_Tree_Mountain map buffer formula not yet documented")
