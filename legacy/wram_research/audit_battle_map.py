#!/usr/bin/env python3
"""Verify corrected Mesen battle mode, enemy HP and party command slots."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CAPTURE_ROOT = ROOT / "mesen_bridge" / "validation" / "gameplay"
ENEMY_BASE = 0x162C
ENEMY_STRIDE = 0xBE
COMMAND_BASE = 0x1F560
COMMAND_STRIDE = 0x0C
COMMAND_OFFSET = 0x04


def load(name: str) -> bytes:
    data = (CAPTURE_ROOT / name).read_bytes()
    if len(data) != 0x20000:
        raise RuntimeError(f"{name}: invalid WRAM size {len(data)}")
    return data


def hp(data: bytes, slot: int) -> int:
    offset = ENEMY_BASE + slot * ENEMY_STRIDE
    return int.from_bytes(data[offset : offset + 2], "little")


def command(data: bytes, slot: int) -> int:
    return data[COMMAND_BASE + slot * COMMAND_STRIDE + COMMAND_OFFSET]


def main() -> int:
    before = load("battle_before.bin")
    menu = load("battle_menu_1.bin")
    after = load("battle_after_round.bin")
    swapped_a = load("battle_commands_guy_attack_arty_defend.bin")
    swapped_b = load("battle_commands_guy_defend_arty_attack.bin")
    slot3 = load("battle_commands_slot3_defend.bin")
    slot4 = load("battle_commands_slot4_defend_running.bin")
    magic = load("battle_command_guy_magic.bin")
    item = load("battle_command_guy_item.bin")
    ip = load("battle_command_guy_ip.bin")
    group_attack = load("battle_group_attack_cursor.bin")
    group_trade = load("battle_group_hold_down.bin")
    group_escape = load("battle_group_hold_up.bin")
    formation_before = load("battle_group_attack_cursor.bin")
    formation_after = load("battle_trade_guy_arty_swapped.bin")
    escape_result = load("battle_escape_result.bin")
    victory_exp = load("battle_victory_result_1.bin")
    victory_gold = load("battle_victory_result_gold.bin")
    victory_return = load("battle_victory_return_field.bin")

    checks = {
        "exploration_01_to_00": (before[0x09A9], menu[0x09A9]) == (1, 0),
        "battle_00_to_01": (before[0x09AA], menu[0x09AA]) == (0, 1),
        "three_enemies_637_hp": [hp(menu, i) for i in range(6)]
        == [637, 637, 637, 0, 0, 0],
        "enemy_hp_tracks_damage_and_removal": [hp(after, i) for i in range(3)]
        == [0, 336, 637],
        "commands_swapped": [command(swapped_a, i) for i in range(2)] == [1, 4]
        and [command(swapped_b, i) for i in range(2)] == [4, 1],
        "slot3_stride": [command(slot3, i) for i in range(4)] == [1, 1, 4, 0],
        "slot4_stride": [command(slot4, i) for i in range(4)] == [1, 1, 4, 4],
        "all_character_commands": [
            command(swapped_a, 0),
            command(magic, 0),
            command(item, 0),
            command(swapped_b, 0),
            command(ip, 0),
        ]
        == [1, 2, 3, 4, 8],
        "legacy_defend_field_unchanged": slot4[0x0D26 + 0x13] == 0,
        "group_menu_options": [
            group_attack[0x0B4E],
            group_trade[0x0B4E],
            group_escape[0x0B4E],
        ]
        == [0x09, 0x0A, 0x0B],
        "battle_formation_swapped_only": formation_before[0x153D:0x1541]
        == bytes.fromhex("02 03 01 04")
        and formation_after[0x153D:0x1541] == bytes.fromhex("03 02 01 04")
        and formation_before[0x0A7B:0x0A7F] == formation_after[0x0A7B:0x0A7F],
        "escape_returns_to_exploration": (
            escape_result[0x09A9],
            escape_result[0x09AA],
        )
        == (1, 0),
        "enemy_hp_is_stale_after_escape": any(
            hp(escape_result, i) > 0 for i in range(6)
        ),
        "victory_rewards": int.from_bytes(victory_exp[0x1605:0x1607], "little")
        == 2689
        and int.from_bytes(victory_gold[0x1608:0x160A], "little") == 4140,
        "victory_result_is_still_battle": (
            victory_gold[0x09A9],
            victory_gold[0x09AA],
        )
        == (0, 1),
        "victory_return_ends_battle": (
            victory_return[0x09A9],
            victory_return[0x09AA],
        )
        == (1, 0),
        "rewards_are_stale_after_return": victory_return[0x1605:0x160A]
        == victory_gold[0x1605:0x160A],
        "victory_clears_enemy_hp": all(hp(victory_return, i) == 0 for i in range(6)),
    }
    payload = {
        "status": "CONFIRMED" if all(checks.values()) else "FAILED",
        "checks": checks,
        "addresses": {
            "exploration_mode": "7E:09A9",
            "battle_mode": "7E:09AA",
            "enemy_hp_base": "7E:162C",
            "enemy_stride": "0xBE",
            "enemy_count": 6,
            "party_command_base": "7F:F560",
            "party_command_stride": "0x0C",
            "command_offset": "0x04",
            "command_values": {
                "Attack": "0x01",
                "Magic": "0x02",
                "Item": "0x03",
                "Defend": "0x04",
                "IP": "0x08"
            },
            "selected_action_or_ability_offset": "0x06",
            "stored_target_mask_offset": "0x00 (see battle_targeting_results)",
            "actor_mask_offset": "0x0A (previously misidentified as target companion)",
            "legacy_character_defend_plus_0x13": "CONTRADICTED",
            "group_menu_selection": "7E:0B4E",
            "group_menu_values": {
                "Fight": "0x09",
                "Trade positions": "0x0A",
                "Escape": "0x0B"
            },
            "battle_formation": "7E:153D-1540",
            "battle_active_rule": "7E:09AA != 0; enemy HP alone is stale after escape",
            "victory_exp": "7E:1605-1606 uint16 little-endian",
            "victory_gold": "7E:1608-1609 uint16 little-endian",
            "reward_validity": "Reward values remain stale after returning to exploration",
        },
    }
    json_path = CAPTURE_ROOT / "battle_results.json"
    md_path = CAPTURE_ROOT / "battle_results.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Battle-WRAM-Audit",
                "",
                f"Status: **{payload['status']}**",
                "",
                "- Gegner-HP: `7E:162C + slot * 0xBE`, uint16 LE.",
                "- Party-Command: `7F:F560 + slot * 0x0C + 0x04`.",
                "- Attack `01`, Defend `04`.",
                "- Permanenter Charakterblock `+0x13` blieb unverändert und ist widerlegt.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "CONFIRMED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
