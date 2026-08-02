#!/usr/bin/env python3
"""Verify the fixed 36-slot battle spell menu and its scrolling render pane."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_ROOT = ROOT / "wram_discovery" / "mesen_bridge" / "validation" / "gameplay"
SPELL_START = 0x0DBF
SPELL_COUNT = 36
ROW_START = 0x3146
ROW_STRIDE = 0x80
RIGHT_COLUMN_OFFSET = 0x1C
COLUMN_BYTES = 0x1C

EXPECTED_IDS = bytes.fromhex(
    "26 24 02 08 0B 0D 12 1B 1F 01 04 05 0A 0F 13 17"
    + " FF" * 20
)
EXPECTED_NAMES = [
    "Reset",
    "Warp",
    "Thunder",
    "Dragon",
    "Ice Valk",
    "Destroy",
    "Absorb",
    "Champion",
    "Fry",
    "Bolt",
    "Fireball",
    "Firebird",
    "Blizzard",
    "Coma",
    "Fake",
    "Courage",
]
EXPECTED_COSTS = [0, 0, 26, 23, 24, 10, 1, 17, 18, 11, 6, 19, 8, 4, 5, 7]


def load(name: str) -> bytes:
    data = (CAPTURE_ROOT / name).read_bytes()
    if len(data) != 0x20000:
        raise RuntimeError(f"{name}: invalid WRAM size {len(data)}")
    return data


def parse_column(data: bytes, start: int) -> tuple[str, int, int] | None:
    raw = data[start : start + COLUMN_BYTES]
    text = "".join(
        chr(value) if 32 <= value <= 126 else " " for value in raw[0::2]
    ).strip()
    if not text or ":" not in text:
        return None
    name, raw_cost = text.rsplit(":", 1)
    return name.strip(), int(raw_cost.strip()), raw[1]


def rendered_entries(data: bytes, window_start: int, rows: int) -> dict[int, tuple[str, int, int]]:
    result: dict[int, tuple[str, int, int]] = {}
    for row in range(rows):
        base = ROW_START + row * ROW_STRIDE
        left = parse_column(data, base)
        right = parse_column(data, base + RIGHT_COLUMN_OFFSET)
        if left:
            result[window_start + row * 2] = left
        if right:
            result[window_start + row * 2 + 1] = right
    return result


def cursor(data: bytes) -> tuple[int, int, int, int, int, int]:
    return (
        data[0x0011],
        data[0x0012],
        data[0x0013],
        data[0x0014],
        data[0x0100],
        data[0x0101],
    )


def main() -> int:
    true_top = load("battle_magic_cursor_true_top.bin")
    scrolled = load("battle_magic_cursor_1.bin")
    champion = load("battle_magic_cursor_2_champion.bin")
    fry = load("battle_magic_cursor_3_fry.bin")
    first_empty = load("battle_magic_cursor_16_first_unavailable.bin")
    empty_attempt = load("battle_magic_first_unavailable_confirm_attempt.bin")
    true_end = load("battle_magic_cursor_true_end.bin")
    fireball_before = load("battle_fireball_before.bin")
    fireball_selected = load("battle_fireball_after_select.bin")
    fireball_executed = load("battle_fireball_after_execute.bin")

    entries = rendered_entries(true_top, 0, 7)
    entries.update(rendered_entries(scrolled, 6, 5))
    names = [entries[index][0] for index in range(16)]
    costs = [entries[index][1] for index in range(16)]
    attributes = [entries[index][2] for index in range(16)]

    checks = {
        "fixed_36_slot_spell_array": true_top[SPELL_START : SPELL_START + SPELL_COUNT]
        == EXPECTED_IDS,
        "rendered_names_follow_array_order": names == EXPECTED_NAMES,
        "randomized_live_costs": costs == EXPECTED_COSTS,
        "noncombat_spells_visible_but_disabled": attributes[:2] == [0x24, 0x24],
        "combat_spells_available_with_471_mp": attributes[2:] == [0x20] * 14,
        "true_top_cursor": cursor(true_top) == (0, 0, 0, 0, 0x08, 0x20),
        "scrolled_absorb_cursor": cursor(scrolled) == (6, 6, 0, 0, 0x08, 0x20),
        "champion_horizontal_cursor": cursor(champion) == (6, 7, 1, 0, 0x78, 0x20),
        "fry_vertical_cursor": cursor(fry) == (6, 8, 0, 1, 0x08, 0x2C),
        "first_empty_slot": cursor(first_empty) == (8, 16, 0, 4, 0x08, 0x50)
        and first_empty[SPELL_START + 16] == 0xFF,
        "empty_slot_confirmation_rejected": cursor(empty_attempt) == cursor(first_empty)
        and empty_attempt[0x0D3C:0x0D3E] == first_empty[0x0D3C:0x0D3E],
        "true_end_cursor": cursor(true_end) == (24, 35, 1, 5, 0x78, 0x5C)
        and true_end[SPELL_START + 35] == 0xFF,
        "fireball_precondition": cursor(fireball_before)
        == (0, 10, 0, 5, 0x08, 0x5C)
        and fireball_before[SPELL_START + 10] == 0x04
        and int.from_bytes(fireball_before[0x0D3C:0x0D3E], "little") == 471,
        "fireball_selection_stores_spell_id": fireball_selected[0x1F564]
        == 0x02
        and fireball_selected[0x1F566] == 0x04
        and int.from_bytes(fireball_selected[0x0D3C:0x0D3E], "little") == 471,
        "fireball_execution_consumes_live_cost": int.from_bytes(
            fireball_executed[0x0D3C:0x0D3E], "little"
        )
        == 465,
    }
    payload = {
        "status": "CONFIRMED" if all(checks.values()) else "FAILED",
        "checks": checks,
        "addresses": {
            "guy_spell_slots": "7E:0DBF-0DE2 (36 bytes)",
            "window_first_absolute_index": "7E:0011",
            "selected_absolute_index": "7E:0012",
            "selected_column": "7E:0013 (00 left, 01 right)",
            "selected_visible_row": "7E:0014",
            "cursor_xy": "7E:0100-0101",
            "prompt": "7E:3046 interleaved ASCII",
            "first_rendered_row": "7E:3146",
            "row_stride": "0x80",
            "right_column_offset": "0x1C",
            "availability_attribute": "column + 0x01: 20 usable, 24 disabled",
        },
        "guy_current_mp": 471,
        "spells": [
            {
                "absolute_index": index,
                "spell_id": f"0x{EXPECTED_IDS[index]:02X}",
                "name": names[index],
                "live_cost": costs[index],
                "available": attributes[index] == 0x20,
                "render_attribute": f"0x{attributes[index]:02X}",
            }
            for index in range(16)
        ],
        "conclusion": (
            "Battle uses the same fixed 36-slot order as the field spell menu. "
            "Randomized costs must be read from live rendered rows. Reset/Warp "
            "remain visible but disabled; FF slots remain navigable and reject confirm. "
            "Fireball stored spell ID 04 and consumed its live cost of 6 MP only "
            "when the action executed."
        ),
        "execution_test": {
            "spell": "Fireball",
            "absolute_index": 10,
            "spell_id": "0x04",
            "battle_command": "0x02",
            "current_mp_address": "7E:0D3C-0D3D",
            "before": 471,
            "after_selection": 471,
            "after_execution": 465,
            "live_cost": 6,
        },
    }
    json_path = CAPTURE_ROOT / "battle_magic_menu_results.json"
    md_path = CAPTURE_ROOT / "battle_magic_menu_results.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Battle-Magic-Menü-Audit",
                "",
                f"Status: **{payload['status']}**",
                "",
                "- 36 feste Spellslots bei Guy: `7E:0DBF-0DE2`.",
                "- Fensterstart `7E:0011`, absoluter Cursorindex `7E:0012`.",
                "- Spalte `7E:0013`, sichtbare Zeile `7E:0014`.",
                "- Renderzeilen ab `7E:3146`, Stride `0x80`, rechte Spalte `+0x1C`.",
                "- Renderattribut `20` ausführbar, `24` deaktiviert.",
                "- Livekosten stammen aus der randomisierten ROM und weichen von Vanilla-Daten ab.",
                "- Leere `FF`-Slots sind navigierbar; Bestätigen wird ignoriert.",
                "- Fireball speicherte Spell-ID `04`; MP sanken erst bei Ausführung von `471` auf `465`.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "CONFIRMED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
