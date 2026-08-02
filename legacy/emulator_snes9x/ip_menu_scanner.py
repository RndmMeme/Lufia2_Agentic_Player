import json
import logging
import os
import time
from typing import Dict, List, Optional


RAM_MAP_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ram_map.json")
ITEMS_SPELLS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "items_spells.json")
IP_SKILLS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ip_skills.json")

EQUIP_SLOT_ORDER = [
    ("Weapon", "Weapon"),
    ("Armor", "Armor"),
    ("Hands", "Hands"),
    ("Headwear", "Headwear"),
    ("Accessories", "Accessories"),
    ("Jewels", "Jewels"),
]

PANE_WIDTH = 32
IP_NAME_COLUMN = 13
LEGACY_HELPER_DELTA = 0x2314
IP_ROW_STRIDE = 0x80
IP_ROW_RENDER_BYTES = 0x40
IP_AVAILABLE_ATTRIBUTE = 0x20
IP_UNAVAILABLE_ATTRIBUTE = 0x24


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


RAM_MAP = _load_json(RAM_MAP_PATH)
ITEMS_SPELLS = _load_json(ITEMS_SPELLS_PATH)
IP_SKILLS = _load_json(IP_SKILLS_PATH)

ITEM_LOOKUP: Dict[str, str] = {}
for category_items in ITEMS_SPELLS.values():
    if not isinstance(category_items, dict):
        continue
    for key, value in category_items.items():
        ITEM_LOOKUP[str(key).upper()] = str(value)

def _normalize_ip_name(value: str) -> str:
    return "".join(char for char in str(value).casefold() if char.isalnum())


IP_SKILL_LOOKUP = {
    _normalize_ip_name(entry.get("name", "")): entry
    for entry in IP_SKILLS
    if isinstance(entry, dict)
}


def _hex_to_int(value):
    return int(str(value), 16)


def _wram_offset(value):
    raw = _hex_to_int(value)
    if raw >= 0xA30000:
        raw -= 0xA30000
    # ram_map.json still preserves the historic Snes9x helper namespace.
    # Mesen exposes the real 128 KiB snesWorkRam image, whose corresponding
    # helper block is shifted by 0x2314 for the fields used by this scanner.
    if raw >= LEGACY_HELPER_DELTA:
        raw -= LEGACY_HELPER_DELTA
    return raw


def _decode_even_ascii(raw):
    data = raw[::2]
    return "".join(chr(b) if 32 <= b <= 126 else " " for b in data)


def _clean_pane_text(text: str) -> str:
    return " ".join(str(text or "").replace("$", "").split()).strip()


def _wait_for_dump(memory_reader, timeout_sec=1.5):
    memory_reader.get_latest_dump()
    memory_reader.send_command("DUMP")
    deadline = time.time() + max(0.2, timeout_sec)
    while time.time() < deadline:
        dump_hex = memory_reader.get_latest_dump()
        if dump_hex:
            try:
                return bytes.fromhex(dump_hex)
            except ValueError:
                logging.warning("IP scan: received malformed dump payload.")
                return None
        time.sleep(0.05)
    logging.warning("IP scan: timed out waiting for WRAM dump.")
    return None


def _read_equipped_slots(wram: bytes, char_name: str) -> List[Dict[str, object]]:
    individual_offsets = RAM_MAP["characters"]["individual_offsets"]
    char_offsets = individual_offsets.get(char_name)
    if not char_offsets:
        return []

    slots = []
    for slot_number, (slot_label, slot_key) in enumerate(EQUIP_SLOT_ORDER, start=1):
        offset = _wram_offset(char_offsets[slot_key])
        raw = bytes(wram[offset : offset + 2])
        item_hex = raw.hex().upper()
        slots.append(
            {
                "slot": slot_number,
                "slot_label": slot_label,
                "item_hex": item_hex,
                "item_name": ITEM_LOOKUP.get(item_hex, f"Unknown Item {item_hex}"),
            }
        )
    return slots


def _build_signature(equipped_slots: List[Dict[str, object]]) -> str:
    return "|".join(str(slot.get("item_hex", "0000")) for slot in equipped_slots)


def _parse_visible_ip_rows(wram: bytes, equipped_slots: List[Dict[str, object]]) -> Dict[int, Dict[str, object]]:
    offsets = RAM_MAP["offsets"]
    first_row = _wram_offset(offsets["EquipmentFirstEntryStart"])
    parsed: Dict[int, Dict[str, object]] = {}
    for row_index, slot in enumerate(equipped_slots):
        start = first_row + row_index * IP_ROW_STRIDE
        raw = wram[start : start + IP_ROW_RENDER_BYTES]
        if len(raw) != IP_ROW_RENDER_BYTES:
            continue
        raw_row = "".join(
            chr(value) if 32 <= value <= 126 else " " for value in raw[1::2]
        ).rstrip()
        render_attribute = raw[2]
        row_clean = _clean_pane_text(raw_row)
        rendered_gear_name = raw_row[:IP_NAME_COLUMN].strip()
        ip_name = raw_row[IP_NAME_COLUMN:].strip()
        if not row_clean or not rendered_gear_name or not ip_name:
            continue

        parsed[int(slot["slot"])] = {
            **slot,
            "rendered_gear_name": rendered_gear_name,
            "ip_name": ip_name,
            "raw_row_text": raw_row,
            "render_attribute": render_attribute,
            "available_from_pane": render_attribute == IP_AVAILABLE_ATTRIBUTE,
        }
    return parsed


class BattleIPMenuCache:
    def __init__(self):
        self._cache: Dict[str, List[Dict[str, object]]] = {}
        self._battle_live: Dict[str, List[Dict[str, object]]] = {}

    def clear_battle(self):
        self._battle_live.clear()

    def inject_into_info(self, info: Dict[str, object]):
        char_stats = info.get("char_stats", {}) if isinstance(info, dict) else {}
        if not isinstance(char_stats, dict):
            return
        for char_name, entries in self._battle_live.items():
            if char_name in char_stats and isinstance(char_stats[char_name], dict):
                char_stats[char_name]["ip_attacks"] = entries

    def get_live_for_character(self, char_name: str) -> Optional[List[Dict[str, object]]]:
        return self._battle_live.get(char_name)

    def ensure_character_ip_attacks(self, memory_reader, macro_executor, char_name: str, current_ip: int) -> List[Dict[str, object]]:
        base_wram = _wait_for_dump(memory_reader)
        if not base_wram:
            return []

        equipped_slots = _read_equipped_slots(base_wram, char_name)
        if not equipped_slots:
            return []

        signature = f"{char_name}:{_build_signature(equipped_slots)}"
        cached = self._cache.get(signature)
        if cached:
            self._battle_live[char_name] = cached
            return cached

        macro_executor.open_ip_menu()
        time.sleep(0.25)
        top_dump = _wait_for_dump(memory_reader)
        macro_executor.close_menu_level()
        parsed_rows = _parse_visible_ip_rows(top_dump, equipped_slots) if top_dump else {}

        entries: List[Dict[str, object]] = []
        for slot in equipped_slots:
            slot_number = int(slot["slot"])
            row = parsed_rows.get(slot_number)
            if not row:
                continue
            ip_name = str(row.get("ip_name", "")).strip()
            meta = IP_SKILL_LOOKUP.get(_normalize_ip_name(ip_name), {})
            cost = int(meta.get("cost", 0) or 0)
            entries.append(
                {
                    "slot": slot_number,
                    "slot_label": slot.get("slot_label"),
                    "gear_name": slot.get("item_name"),
                    "item_hex": slot.get("item_hex"),
                    "name": ip_name,
                    "cost": cost,
                    "description": meta.get("description", ""),
                    "elements": meta.get("elements", []),
                    "properties": meta.get("properties", []),
                    "available": bool(row.get("available_from_pane"))
                    and (current_ip >= cost if cost else True),
                    "available_from_pane": bool(row.get("available_from_pane")),
                    "render_attribute": row.get("render_attribute"),
                    "raw_row_text": row.get("raw_row_text", ""),
                }
            )

        if entries:
            self._cache[signature] = entries
            self._battle_live[char_name] = entries

        return entries
