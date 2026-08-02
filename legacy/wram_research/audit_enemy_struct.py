#!/usr/bin/env python3
"""Verify the character-like six-slot enemy combat-stat structure."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CAPTURE_ROOT = ROOT / "mesen_bridge" / "validation" / "gameplay"
MONSTER_TABLE = ROOT.parent / "data" / "monster_overworld_sprites.txt"
STRUCT_BASE = 0x1618
STRIDE = 0xBE
COUNT = 6
OFFSETS = {
    "level": (0x11, 1),
    "status": (0x12, 1),
    "current_hp": (0x14, 2),
    "current_mp": (0x16, 2),
    "max_hp": (0x28, 2),
    "max_mp": (0x2A, 2),
    "attack": (0x2C, 2),
    "defense": (0x2E, 2),
    "strength": (0x30, 2),
    "agility": (0x32, 2),
    "intelligence": (0x34, 2),
    "guts": (0x36, 2),
    "magic_resistance": (0x38, 2),
}


def load(name: str) -> bytes:
    data = (CAPTURE_ROOT / name).read_bytes()
    if len(data) != 0x20000:
        raise RuntimeError(f"{name}: invalid WRAM size {len(data)}")
    return data


def value(data: bytes, slot: int, field: str) -> int:
    offset, size = OFFSETS[field]
    start = STRUCT_BASE + slot * STRIDE + offset
    return int.from_bytes(data[start : start + size], "little")


def row(data: bytes, slot: int) -> dict[str, int]:
    return {field: value(data, slot, field) for field in OFFSETS}


def enemy_name(data: bytes, slot: int) -> str:
    start = STRUCT_BASE + slot * STRIDE + 0x03
    return data[start : start + 13].decode("ascii").rstrip("\0 ")


def enemy_id(data: bytes, slot: int) -> int:
    return data[STRUCT_BASE + slot * STRIDE + 0x53]


def monster_table() -> dict[int, tuple[int, str]]:
    result = {}
    for line in MONSTER_TABLE.read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) == 3:
            result[int(parts[0], 16)] = (int(parts[1], 16), parts[2])
    return result


def main() -> int:
    before = load("battle_menu_1.bin")
    after = load("battle_after_round.bin")
    paralyzed = load("battle_enemy_freeze_ball_after_round.bin")
    ramia = load("battle_enemy_species_2_idle.bin")
    initial = [row(before, slot) for slot in range(COUNT)]
    final = [row(after, slot) for slot in range(COUNT)]
    monsters = monster_table()
    expected_garbost = {
        "level": 50,
        "status": 0,
        "current_hp": 637,
        "current_mp": 32,
        "max_hp": 637,
        "max_mp": 32,
        "attack": 135,
        "defense": 298,
        "strength": 0,
        "agility": 154,
        "intelligence": 92,
        "guts": 120,
        "magic_resistance": 50,
    }
    checks = {
        "three_identical_garbost_stat_blocks": initial[:3]
        == [expected_garbost] * 3,
        "enemy_name_is_inline_ascii": [
            enemy_name(before, slot) for slot in range(3)
        ] == ["Garbost"] * 3
        and [enemy_name(ramia, slot) for slot in range(3)] == ["Ramia"] * 3,
        "enemy_id_matches_abyssonym_table": [
            enemy_id(before, slot) for slot in range(3)
        ] == [0x54] * 3
        and [enemy_id(ramia, slot) for slot in range(3)] == [0x3B] * 3
        and monsters[0x54][1] == "Garbost"
        and monsters[0x3B][1] == "Ramia",
        "second_species_uses_same_stat_offsets": [
            row(ramia, slot) for slot in range(3)
        ] == [
            {
                "level": 50,
                "status": 0,
                "current_hp": 575,
                "current_mp": 108,
                "max_hp": 575,
                "max_mp": 108,
                "attack": 256,
                "defense": 212,
                "strength": 0,
                "agility": 44,
                "intelligence": 88,
                "guts": 112,
                "magic_resistance": 66,
            }
        ] * 3,
        "unused_slots_have_zero_core_stats": all(
            all(value == 0 for value in item.values()) for item in initial[3:]
        ),
        "current_hp_changes_at_struct_plus_0x14": [
            item["current_hp"] for item in final[:3]
        ] == [0, 336, 637],
        "max_hp_remains_at_struct_plus_0x28": [
            item["max_hp"] for item in final[:3]
        ] == [637, 637, 637],
        "disabled_status_bit_on_defeated_enemy": final[0]["status"] == 0x04
        and final[1]["status"] == 0
        and final[2]["status"] == 0,
        "freeze_ball_sets_paralyze_bit_0x08": value(
            paralyzed, 2, "status"
        ) == 0x08
        and value(paralyzed, 2, "current_hp") == 637,
        "nonvolatile_combat_stats_remain_stable": all(
            final[slot][field] == initial[slot][field]
            for slot in range(3)
            for field in OFFSETS
            if field not in {"status", "current_hp"}
        ),
    }
    payload = {
        "status": "CONFIRMED" if all(checks.values()) else "FAILED",
        "checks": checks,
        "layout": {
            "struct_base": "7E:1618 + slot*0xBE",
            "slot_count": COUNT,
            "stride": "0xBE",
            "name": "struct +0x03, 13 ASCII bytes",
            "enemy_id": "struct +0x53, uint8; Abyssonym monster table index",
            "status_addresses": [
                "7E:162A",
                "7E:16E8",
                "7E:17A6",
                "7E:1864",
                "7E:1922",
                "7E:19E0",
            ],
            "status_bits": {
                "poison": "0x01, inherited from identical party layout",
                "silence": "0x02, inherited from identical party layout",
                "disabled": "0x04, live confirmed",
                "paralyze": "0x08, live confirmed",
                "confusion": "0x10, inherited from identical party layout",
                "sleep": "0x20, inherited from identical party layout",
            },
            "offsets": {
                field: f"0x{offset:02X}" for field, (offset, _) in OFFSETS.items()
            },
            "old_hp_anchor": "7E:162C + slot*0xBE = struct + 0x14",
        },
        "live_values": {
            "enemy": "Garbost",
            "enemy_id": "0x54",
            "slots_0_to_2_before": initial[:3],
            "slots_0_to_2_after_round": final[:3],
            "freeze_ball_target_slot_2": row(paralyzed, 2),
            "second_species": {
                "name": "Ramia",
                "enemy_id": "0x3B",
                "slots_0_to_2": [row(ramia, slot) for slot in range(3)],
            },
        },
        "confidence": {
            "current_hp": "live effect confirmed",
            "status_disabled_0x04": "live death transition confirmed",
            "status_paralyze_0x08": "live Freeze ball transition confirmed",
            "remaining_stat_names": "confirmed by exact character-layout alignment and stable identical enemy blocks",
            "other_status_bits": "accepted inference from the identical party combat-stat layout",
        },
    }
    json_path = CAPTURE_ROOT / "enemy_struct_results.json"
    md_path = CAPTURE_ROOT / "enemy_struct_results.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Enemy-Struct-WRAM-Audit",
                "",
                f"Status: **{payload['status']}**",
                "",
                "- Vollstaendiger Struct: `7E:1618 + slot*0xBE`.",
                "- Der alte Anker `7E:162C` ist `CurrentHP` bei Struct `+0x14`.",
                "- Status liegt bei `+0x12`; Tod setzte live Bit `04`.",
                "- Freeze ball setzte am unbeschaedigten Ziel live Paralyze-Bit `08`.",
                "- Current/Max HP und MP sowie ATP, DFP, STR, AGL, INT, GUT und MGR folgen den Charakteroffsets.",
                "- Weitere Statusbits benoetigen kontrollierte Gift/Schlaf/Paralyse-Tests.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "CONFIRMED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
