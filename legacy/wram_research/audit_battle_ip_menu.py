#!/usr/bin/env python3
"""Verify the six live-captured battle IP-menu rows against Mesen WRAM."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from emulator import ip_menu_scanner


CAPTURE_ROOT = ROOT / "wram_discovery" / "mesen_bridge" / "validation" / "gameplay"
CAPTURES = [
    "battle_ip_cursor_1_zirco_ax.bin",
    "battle_ip_cursor_2_zircon_plate_manual.bin",
    "battle_ip_cursor_3_mage_shield_manual.bin",
    "battle_ip_cursor_4_old_helmet_manual.bin",
    "battle_ip_cursor_5_sonic_ring_manual.bin",
    "battle_ip_cursor_6_black_eye_manual.bin",
]
EXPECTED_ITEMS = bytes.fromhex("78 00 DE 00 F9 00 3A 01 53 01 87 01")
EXPECTED_GEAR = [
    "Zirco ax",
    "Zircon plate",
    "Mage shield",
    "Old helmet",
    "Sonic ring",
    "Black eye",
]
EXPECTED_IP = [
    "Holy mirror",
    "Anger mirror",
    "Sleep stinger",
    "Bomb attack",
    "Sluggish",
    "Hardboiled",
]


def load(name: str) -> bytes:
    data = (CAPTURE_ROOT / name).read_bytes()
    if len(data) != 0x20000:
        raise RuntimeError(f"{name}: invalid WRAM size {len(data)}")
    return data


def main() -> int:
    captures = [load(name) for name in CAPTURES]
    sleep_before = load("battle_sleep_stinger_before.bin")
    sleep_selected = load("battle_sleep_stinger_after_select.bin")
    sleep_targeted = load("battle_sleep_stinger_target_confirmed.bin")
    sleep_executed = load("battle_sleep_stinger_after_execute.bin")
    slots = ip_menu_scanner._read_equipped_slots(captures[0], "Guy")
    rows = ip_menu_scanner._parse_visible_ip_rows(captures[0], slots)
    parsed_gear = [rows[index]["rendered_gear_name"] for index in range(1, 7)]
    parsed_ip = [rows[index]["ip_name"] for index in range(1, 7)]
    parsed_costs = [
        ip_menu_scanner.IP_SKILL_LOOKUP[
            ip_menu_scanner._normalize_ip_name(name)
        ]["cost"]
        for name in parsed_ip
    ]
    current_ip = captures[0][0x0DE5]
    pane_available = [rows[index]["available_from_pane"] for index in range(1, 7)]
    render_attributes = [rows[index]["render_attribute"] for index in range(1, 7)]
    expected_available = [current_ip >= cost for cost in parsed_costs]

    checks = {
        "cursor_index_0_to_5": [data[0x0014] for data in captures]
        == list(range(6)),
        "cursor_index_double_mirror": [data[0x0012] for data in captures]
        == [0, 2, 4, 6, 8, 10],
        "cursor_y_stride_0x0c": [data[0x0101] for data in captures]
        == [0x20, 0x2C, 0x38, 0x44, 0x50, 0x5C],
        "equipment_working_list": all(
            data[0x1357:0x1363] == EXPECTED_ITEMS for data in captures
        ),
        "six_rendered_gear_names": parsed_gear == EXPECTED_GEAR,
        "six_rendered_ip_names": parsed_ip == EXPECTED_IP,
        "six_ip_costs_resolve": parsed_costs == [164, 216, 96, 64, 128, 8],
        "guy_current_ip": current_ip == 96,
        "availability_attributes": render_attributes
        == [0x24, 0x24, 0x20, 0x20, 0x24, 0x20],
        "pane_matches_ip_greater_or_equal_cost": pane_available
        == expected_available,
        "sleep_stinger_precondition": sleep_before[0x0DE5] == 96
        and sleep_before[0x0014] == 2
        and sleep_before[0x3249] == 0x20,
        "sleep_stinger_selection_keeps_ip": sleep_selected[0x0DE5] == 96
        and sleep_selected[0x1F564] == 0x08
        and sleep_selected[0x1F566] == 0x1B,
        "sleep_stinger_target_confirmation_keeps_ip": sleep_targeted[0x0DE5]
        == 96,
        "sleep_stinger_execution_consumes_96_ip": sleep_executed[0x0DE5]
        == 0,
        "row_stride_0x80": all(
            captures[0][0x3148 + row * 0x80] != 0 for row in range(6)
        ),
    }
    payload = {
        "status": "CONFIRMED" if all(checks.values()) else "FAILED",
        "checks": checks,
        "addresses": {
            "cursor_index": "7E:0014 (00-05)",
            "cursor_y": "7E:0101 (20 + row*0C)",
            "equipment_working_list": "7E:1357-1362 (six uint16 LE item IDs)",
            "prompt": "7E:3046 interleaved ASCII",
            "first_rendered_row": "7E:3147",
            "rendered_row_stride": "0x80",
            "ip_name_in_row": "row + 0x1B",
            "availability_attribute": "row + 0x02: 20 usable, 24 insufficient IP",
            "rendered_pane_end": "7E:3447",
            "guy_current_ip": "7E:0DE5 = 96",
        },
        "rows": [
            {
                "slot": index,
                "item_id": slots[index - 1]["item_hex"],
                "gear": parsed_gear[index - 1],
                "ip": parsed_ip[index - 1],
                "cost": parsed_costs[index - 1],
                "available": pane_available[index - 1],
                "render_attribute": f"0x{render_attributes[index - 1]:02X}",
            }
            for index in range(1, 7)
        ],
        "conclusion": (
            "The menu materializes six equipment IDs plus rendered item/IP text. "
            "No separate six-entry IP-skill-ID list was observed in WRAM. "
            "Sleep Stinger selection and targeting kept Guy at 96 IP; actual "
            "execution consumed all 96 IP and left zero."
        ),
        "execution_test": {
            "ability": "Sleep stinger",
            "cost": 96,
            "current_ip_address": "7E:0DE5",
            "before": 96,
            "after_selection": 96,
            "after_target_confirmation": 96,
            "after_execution": 0,
            "battle_command": "0x08",
            "observed_selected_action": "0x1B",
        },
    }
    json_path = CAPTURE_ROOT / "battle_ip_menu_results.json"
    md_path = CAPTURE_ROOT / "battle_ip_menu_results.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Battle-IP-Menü-Audit",
                "",
                f"Status: **{payload['status']}**",
                "",
                "- Cursorindex: `7E:0014`, Werte `00` bis `05`.",
                "- Cursor-Y: `7E:0101`, `20 + Zeile * 0x0C`.",
                "- Equipment-Arbeitsliste: `7E:1357-1362`, sechs Item-IDs.",
                "- Renderzeilen: `7E:3147 + Zeile * 0x80`.",
                "- IP-Name innerhalb einer Zeile: `+0x1B`.",
                "- Nutzbarkeitsattribut bei `Zeile + 0x02`: `20` ausführbar, `24` zu wenig IP.",
                "- Regel bestätigt: `aktuelle IP >= Kosten`; Guy hatte `96` IP.",
                "- Sleep stinger: Auswahl/Ziel hielten IP bei `96`; erst die Ausführung senkte `7E:0DE5` auf `0`.",
                "- Keine separate Sechserliste aus IP-Fähigkeits-IDs beobachtet.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "CONFIRMED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
