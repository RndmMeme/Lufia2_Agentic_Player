#!/usr/bin/env python3
"""Verify the fixed 96-slot battle item menu and raw inventory alignment."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_ROOT = ROOT / "wram_discovery" / "mesen_bridge" / "validation" / "gameplay"
INVENTORY_START = 0x0A8D
INVENTORY_SIZE = 0xC0
INVENTORY_SLOTS = 96
ROW_START = 0x3147
ROW_STRIDE = 0x80
ROW_BYTES = 0x40


def load(name: str) -> bytes:
    data = (CAPTURE_ROOT / name).read_bytes()
    if len(data) != 0x20000:
        raise RuntimeError(f"{name}: invalid WRAM size {len(data)}")
    return data


def cursor(data: bytes) -> tuple[int, int, int, int, int, int]:
    return (
        data[0x0011],
        data[0x0012],
        data[0x0013],
        data[0x0014],
        data[0x0100],
        data[0x0101],
    )


def parse_row(data: bytes, row: int) -> tuple[str, int | None, int | None]:
    start = ROW_START + row * ROW_STRIDE
    raw = data[start : start + ROW_BYTES]
    text = "".join(
        chr(value) if 32 <= value <= 126 else " " for value in raw[1::2]
    ).strip()
    if not text or ":" not in text:
        return "", None, None
    name, raw_qty = text.rsplit(":", 1)
    return name.strip(), int(raw_qty.strip()), raw[2]


def main() -> int:
    top = load("battle_item_cursor_1.bin")
    charred = load("battle_item_cursor_slot2_charred_newt.bin")
    curselifter = load("battle_item_cursor_2_curselifter.bin")
    true_end = load("battle_item_cursor_true_end.bin")
    charred_before = load("battle_charred_newt_before.bin")
    charred_selected = load("battle_charred_newt_after_select.bin")
    charred_executed = load("battle_charred_newt_after_execute.bin")

    rows = [parse_row(top, index) for index in range(7)]
    checks = {
        "slot1_empty": top[INVENTORY_START : INVENTORY_START + 2]
        == bytes.fromhex("00 00")
        and rows[0] == ("", None, None),
        "slot2_charred_newt": top[INVENTORY_START + 2 : INVENTORY_START + 4]
        == bytes.fromhex("01 02")
        and rows[1] == ("Charred newt", 1, 0x20),
        "slot3_curselifter": top[INVENTORY_START + 4 : INVENTORY_START + 6]
        == bytes.fromhex("2C 02")
        and rows[2] == ("Curselifter", 1, 0x24),
        "slot4_escape": rows[3] == ("Escape", 15, 0x24),
        "slot5_shriek": rows[4] == ("Shriek", 1, 0x20),
        "slot6_freeze_ball": rows[5] == ("Freeze ball", 1, 0x20),
        "top_empty_cursor": cursor(top) == (0, 0, 0, 0, 0x08, 0x20),
        "slot2_cursor": cursor(charred) == (0, 2, 0, 1, 0x08, 0x2C),
        "slot3_cursor": cursor(curselifter) == (0, 4, 0, 2, 0x08, 0x38),
        "true_96_slot_end": cursor(true_end)
        == (0xB4, 0xBE, 0, 5, 0x08, 0x5C),
        "last_slot_has_two_bytes": true_end[
            INVENTORY_START + 0xBE : INVENTORY_START + 0xC0
        ]
        == bytes.fromhex("00 00"),
        "charred_newt_precondition": charred_before[
            INVENTORY_START + 2 : INVENTORY_START + 4
        ]
        == bytes.fromhex("01 02")
        and int.from_bytes(charred_before[0x0D3C:0x0D3E], "little") == 465,
        "item_selection_stores_raw_pair": charred_selected[0x1F564] == 0x03
        and charred_selected[0x1F566:0x1F568] == bytes.fromhex("01 02")
        and int.from_bytes(charred_selected[0x0D3C:0x0D3E], "little") == 465,
        "selection_transition_temporarily_clears_slot": charred_selected[
            INVENTORY_START + 2 : INVENTORY_START + 4
        ]
        == bytes.fromhex("00 00"),
        "item_execution_consumes_stack_and_restores_mp": charred_executed[
            INVENTORY_START + 2 : INVENTORY_START + 4
        ]
        == bytes.fromhex("00 00")
        and int.from_bytes(charred_executed[0x0D3C:0x0D3E], "little") == 470,
    }
    payload = {
        "status": "CONFIRMED" if all(checks.values()) else "FAILED",
        "checks": checks,
        "addresses": {
            "inventory": "7E:0A8D-0B4C inclusive, 0xC0 bytes, 96 two-byte slots",
            "window_first_byte_offset": "7E:0011",
            "selected_inventory_byte_offset": "7E:0012 = 2*(slot-1)",
            "selected_visible_row": "7E:0014",
            "cursor_xy": "7E:0100-0101",
            "prompt": "7E:3046 interleaved ASCII",
            "first_rendered_row": "7E:3147",
            "rendered_row_stride": "0x80",
            "availability_attribute": "row + 0x02: 20 usable, 24 disabled",
        },
        "semantics": {
            "storage_slot": "Fixed 1-based raw inventory slot, including empty slots.",
            "selected_byte_offset": "Zero-based storage slot index multiplied by two.",
            "occupied_ordinal": "Separate display/reporting concept; must not be used for navigation.",
        },
        "conclusion": (
            "Battle preserves all 96 raw inventory slots, including empties. "
            "The old 0xBF-byte helper length omitted the second byte of slot 96; "
            "the correct length is 0xC0. Charred Newt stored raw pair 01 02 "
            "in the command. The selection transition temporarily cleared the "
            "slot; only the final empty slot together with the +5 MP effect proves execution."
        ),
        "execution_test": {
            "item": "Charred newt",
            "storage_slot": 2,
            "raw_pair": "01 02",
            "battle_command": "0x03",
            "before_mp": 465,
            "after_selection_mp": 465,
            "selection_transition_slot": "00 00 (temporary reservation/removal)",
            "after_execution_mp": 470,
            "slot_after_execution": "00 00",
        },
    }
    json_path = CAPTURE_ROOT / "battle_item_menu_results.json"
    md_path = CAPTURE_ROOT / "battle_item_menu_results.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Battle-Item-Menü-Audit",
                "",
                f"Status: **{payload['status']}**",
                "",
                "- 96 feste Zweibyte-Slots: `7E:0A8D-0B4C`, Länge `0xC0`.",
                "- Slot 1 leer, Charred newt Slot 2, Curselifter Slot 3.",
                "- Auswahlbyteoffset `7E:0012 = 2*(Slot-1)`.",
                "- Renderattribut `20` nutzbar, `24` deaktiviert.",
                "- Leere Slots bleiben im Menü erhalten; keine Komprimierung.",
                "- Charred newt: Command `03`, Rohpaar `01 02`; Auswahlübergang leerte den Slot kurzzeitig. Erst final leerer Slot plus +5 MP beweist die Ausführung.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "CONFIRMED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
