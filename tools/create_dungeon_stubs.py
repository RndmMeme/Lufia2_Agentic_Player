"""Create stub .py files for all dungeons from emulator/maps/Dungeons/."""

import os
from pathlib import Path

DUNGEON_DIR = Path("emulator/maps/Dungeons")
AGENT_DUNGEONS_DIR = Path("agent/dungeons")

STUB_TEMPLATE = '''"""{name} specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class {classname}(BaseDungeon):
    """{name} — puzzle logic not yet implemented."""

    map_id: int = 0  # TODO: assign actual map_id
    name: str = "{name}"

    def tile_address(self, x: int, y: int) -> int:
        raise NotImplementedError("{name} map buffer formula not yet documented")
'''

# Get all dungeon directories
dungeons = sorted([d.name for d in DUNGEON_DIR.iterdir() if d.is_dir()])

for dungeon_name in dungeons:
    # Convert directory name to class name: Alunze_Castle_Basement -> AlunzeCastleBasement
    classname = dungeon_name.replace("_", "").replace("'", "").replace(" ", "")
    # Convert directory name to file name: Alunze_Castle_Basement -> alunze_castle_basement.py
    filename = dungeon_name.lower().replace("'", "").replace(" ", "_") + ".py"
    filepath = AGENT_DUNGEONS_DIR / filename

    if filepath.exists():
        print(f"SKIP: {filename} already exists")
        continue

    content = STUB_TEMPLATE.format(name=dungeon_name, classname=classname)
    filepath.write_text(content, encoding="utf-8")
    print(f"CREATE: {filename}")

print(f"\nDone. {len(dungeons)} dungeon stubs processed.")
