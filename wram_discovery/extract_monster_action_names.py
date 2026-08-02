"""Extract the 256 monster-action labels from a Lufia II ROM.

The FRUE/Terrorwave layout places the two-byte action-name pointer table at
file offset 0x280000. Pointers address null-terminated strings in the same
LoROM bank; byte E0 is the game's leading text control code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


POINTER_TABLE_OFFSET = 0x280000
POINTER_COUNT = 0x100
MAX_NAME_LENGTH = 64


def extract_action_names(rom: bytes) -> list[dict[str, object]]:
    pointer_end = POINTER_TABLE_OFFSET + POINTER_COUNT * 2
    if len(rom) < pointer_end:
        raise ValueError("ROM is too small for the monster-action pointer table")

    entries: list[dict[str, object]] = []
    for action_id in range(POINTER_COUNT):
        pointer_pos = POINTER_TABLE_OFFSET + action_id * 2
        pointer = int.from_bytes(rom[pointer_pos : pointer_pos + 2], "little")
        string_offset = POINTER_TABLE_OFFSET + (pointer & 0x7FFF)
        raw = rom[string_offset : string_offset + MAX_NAME_LENGTH]
        terminator = raw.find(b"\x00")
        if terminator < 0:
            raise ValueError(
                f"Action 0x{action_id:02X} has no terminator near 0x{string_offset:X}"
            )
        raw = raw[:terminator]
        if raw.startswith(b"\xE0"):
            raw = raw[1:]
        name = raw.decode("ascii")
        entries.append(
            {
                "id": action_id,
                "id_hex": f"{action_id:02X}",
                "name": name,
                "pointer": f"{pointer:04X}",
                "rom_offset": f"{string_offset:06X}",
            }
        )
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/monster_action_names.json"),
    )
    args = parser.parse_args()

    rom = args.rom.read_bytes()
    entries = extract_action_names(rom)
    payload = {
        "source_rom": str(args.rom),
        "source_rom_sha1": hashlib.sha1(rom).hexdigest().upper(),
        "pointer_table_rom_offset": f"{POINTER_TABLE_OFFSET:06X}",
        "count": len(entries),
        "entries": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"{len(entries)} action names -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
