"""Join Terrorwave's monster/sprite table with the ROM movement-mode table."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MOVEMENT_TABLE_OFFSET = 0x27F6B5
SPRITE_ID_BASE = 0x80
MOVEMENT_COUNT = 112


def parse_monster_sprites(path: Path) -> list[dict[str, object]]:
    monsters = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        monster_id, sprite_id, name = line.split(maxsplit=2)
        monsters.append(
            {
                "monster_id": int(monster_id, 16),
                "monster_id_hex": monster_id.upper(),
                "overworld_sprite_id": int(sprite_id, 16),
                "overworld_sprite_id_hex": sprite_id.upper(),
                "name": name,
            }
        )
    return monsters


def extract_movements(
    rom: bytes, monsters: list[dict[str, object]]
) -> dict[str, object]:
    table = rom[MOVEMENT_TABLE_OFFSET : MOVEMENT_TABLE_OFFSET + MOVEMENT_COUNT]
    if len(table) != MOVEMENT_COUNT:
        raise ValueError("ROM is too small for Terrorwave's MonsterMoveObject table")

    modes = [
        {
            "overworld_sprite_id": SPRITE_ID_BASE + index,
            "overworld_sprite_id_hex": f"{SPRITE_ID_BASE + index:02X}",
            "movement_mode": value,
            "movement_mode_hex": f"{value:02X}",
            "rom_offset": f"{MOVEMENT_TABLE_OFFSET + index:06X}",
        }
        for index, value in enumerate(table)
    ]
    by_sprite = {
        entry["overworld_sprite_id"]: entry
        for entry in modes
    }
    joined = []
    for monster in monsters:
        sprite_id = int(monster["overworld_sprite_id"])
        movement = by_sprite.get(sprite_id)
        joined.append(
            {
                **monster,
                "movement_mode": movement["movement_mode"] if movement else None,
                "movement_mode_hex": (
                    movement["movement_mode_hex"] if movement else None
                ),
            }
        )

    return {
        "movement_modes_by_overworld_sprite": modes,
        "monsters": joined,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument(
        "--monster-table",
        type=Path,
        default=Path(
            "data/terrorwave_reference/tables/monster_overworld_sprites.txt"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/monster_movement_modes.json"),
    )
    args = parser.parse_args()

    rom = args.rom.read_bytes()
    monsters = parse_monster_sprites(args.monster_table)
    payload = {
        "source_rom": str(args.rom),
        "source_rom_sha1": hashlib.sha1(rom).hexdigest().upper(),
        "authoritative_schema": (
            "Terrorwave tables_list.frue.txt / MonsterMoveObject / "
            "struct_monster_move.txt"
        ),
        "movement_table_rom_offset": f"{MOVEMENT_TABLE_OFFSET:06X}",
        "sprite_id_base": f"{SPRITE_ID_BASE:02X}",
        "count": MOVEMENT_COUNT,
        **extract_movements(rom, monsters),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"{MOVEMENT_COUNT} sprite movement modes and {len(monsters)} monsters "
        f"-> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
