#!/usr/bin/env python3
"""Verify battle target masks from manually controlled Mesen captures."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CAPTURE_ROOT = ROOT / "mesen_bridge" / "validation" / "gameplay"
COMMAND_BASE = 0x1F560
COMMAND_STRIDE = 0x0C
TARGET_MASK_OFFSET = 0x00
COMMAND_OFFSET = 0x04
ACTION_OFFSET = 0x06
ACTOR_MASK_OFFSET = 0x0A
ACTIVE_TARGET_INDEX = 0x0026


def load(name: str) -> bytes:
    data = (CAPTURE_ROOT / name).read_bytes()
    if len(data) != 0x20000:
        raise RuntimeError(f"{name}: invalid WRAM size {len(data)}")
    return data


def record(data: bytes, slot: int = 0) -> bytes:
    start = COMMAND_BASE + slot * COMMAND_STRIDE
    return data[start : start + COMMAND_STRIDE]


def main() -> int:
    enemy_left_active = load("battle_target_enemy_slot3_active_fresh.bin")
    enemy_left = load("battle_target_enemy_index0_attack_stored.bin")
    enemy_middle = load("battle_target_enemy_slot1_arty_command_stored.bin")
    enemy_right = load("battle_target_enemy_slot2_arty_command_stored.bin")
    enemy_all_two = load("battle_target_all_remaining_enemies_fireball_stored.bin")
    enemy_all_three = load("battle_target_enemy_index0_command_stored.bin")
    party_guy = load("battle_target_party_guy_champion_stored.bin")
    party_arty = load("battle_target_party_arty_champion_stored.bin")
    party_selan = load("battle_target_party_selan_champion_stored.bin")
    party_tia = load("battle_target_party_tia_champion_stored.bin")
    party_all = load("battle_target_party_all_champion_stored.bin")

    enemy_records = [
        record(enemy_left, 0),
        record(enemy_middle, 1),
        record(enemy_right, 1),
    ]
    party_records = [
        record(party_guy),
        record(party_arty),
        record(party_selan),
        record(party_tia),
    ]
    checks = {
        "active_enemy_index_is_zero_based": enemy_left_active[ACTIVE_TARGET_INDEX] == 0,
        "enemy_single_target_masks": [
            row[TARGET_MASK_OFFSET] for row in enemy_records
        ] == [0x81, 0x82, 0x84],
        "enemy_all_two_combines_live_bits": record(enemy_all_two)[TARGET_MASK_OFFSET]
        == 0x86,
        "enemy_all_three_combines_live_bits": record(enemy_all_three)[TARGET_MASK_OFFSET]
        == 0x87,
        "party_single_target_masks": [
            row[TARGET_MASK_OFFSET] for row in party_records
        ] == [0x01, 0x02, 0x04, 0x08],
        "party_all_combines_live_bits": record(party_all)[TARGET_MASK_OFFSET] == 0x0F,
        "target_is_record_byte_zero": record(party_guy)[1:10]
        == record(party_arty)[1:10]
        == record(party_selan)[1:10]
        == record(party_tia)[1:10],
        "champion_command_and_spell": all(
            row[COMMAND_OFFSET] == 0x02 and row[ACTION_OFFSET] == 0x1B
            for row in party_records + [record(party_all)]
        ),
        "actor_mask_is_not_target": record(enemy_middle, 1)[ACTOR_MASK_OFFSET]
        == record(enemy_right, 1)[ACTOR_MASK_OFFSET]
        == 0x04,
        "guy_actor_mask": record(enemy_left)[ACTOR_MASK_OFFSET] == 0x02,
    }
    payload = {
        "status": "CONFIRMED" if all(checks.values()) else "FAILED",
        "checks": checks,
        "addresses": {
            "active_temporary_target_index": "7E:0026, zero-based; insufficient to detect R/all mode",
            "party_command_base": "7F:F560",
            "party_command_stride": "0x0C",
            "stored_target_mask_offset": "0x00",
            "command_offset": "0x04",
            "selected_action_offset": "0x06",
            "actor_mask_offset": "0x0A",
        },
        "encoding": {
            "party": {
                "index_bits": ["0x01", "0x02", "0x04", "0x08"],
                "all_four": "0x0F",
            },
            "enemy": {
                "flag": "0x80",
                "confirmed_index_bits": ["0x01", "0x02", "0x04"],
                "confirmed_all_three": "0x87",
                "derived_unseen_index_bits": ["0x08", "0x10", "0x20"],
                "derived_all_six": "0xBF",
            },
        },
        "semantics": [
            "R toggles a temporary all-target mode; it need not be held.",
            "The fixed cursor remains on one target while all-target mode is active.",
            "The confirmed command mask is authoritative for single versus all.",
            "Enemy indices 3-5 are structurally derived because six-enemy encounters are rare and were not forced.",
        ],
    }
    json_path = CAPTURE_ROOT / "battle_targeting_results.json"
    md_path = CAPTURE_ROOT / "battle_targeting_results.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Battle-Targeting-WRAM-Audit",
                "",
                f"Status: **{payload['status']}**",
                "",
                "- Gespeicherte Zielmaske: `7F:F560 + slot*0x0C + 0x00`.",
                "- Gruppe: `01,02,04,08`; alle vier `0F`.",
                "- Gegner: Flag `80` plus Zielbits; live bestaetigt `81,82,84`, alle drei `87`.",
                "- Gegnerbits `08,10,20` und alle sechs `BF` sind strukturell abgeleitet, noch nicht live beobachtet.",
                "- `7E:0026` ist nur der temporaere nullbasierte Cursorindex und erkennt den R/Alle-Modus nicht.",
                "- `command + 0x0A` ist die Akteurmaske, nicht das Ziel.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "CONFIRMED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
