"""Compact decoder for confirmed Mesen WRAM gameplay state."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from emulator.item_db import ITEM_DB
from emulator.map_db import MAP_DB
from emulator.zone_db import zone_for_map


CHARACTER_NAMES = ("Maxim", "Selan", "Guy", "Artea", "Tia", "Dekar", "Lexis")
CHARACTER_BASE = 0x0BAA
CHARACTER_STRIDE = 0xBE
ENEMY_BASE = 0x1618
ENEMY_STRIDE = 0xBE
DIRECTION_NAMES = {0x00: "south", 0x02: "west", 0x04: "north", 0x06: "east"}
BLOCKED_NAMES = {0x00: "north", 0x01: "south", 0x02: "west", 0x03: "east", 0xFF: None}
DATA_ROOT = Path(__file__).resolve().parent.parent / "data"


def _flag_masks(filename: str) -> dict[str, int]:
    records = json.loads((DATA_ROOT / filename).read_text(encoding="utf-8"))
    masks = {}
    for name, record in records.items():
        raw = str(record.get("obtained_value", "")).replace(" ", "")
        if raw and set(raw) <= {"0", "1"}:
            masks[name] = int(raw, 2)
    return masks


PROGRESSION_FLAG_MASKS = {
    **_flag_masks("scenario_items.json"),
    **_flag_masks("tool_items.json"),
}


def u16(data: bytes, offset: int) -> int:
    return data[offset] | (data[offset + 1] << 8)


@dataclass(frozen=True)
class Combatant:
    slot: int
    name: str
    identity: int
    level: int
    status: int
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    ip: int | None = None
    attack: int | None = None
    defense: int | None = None
    strength: int | None = None
    agility: int | None = None
    intelligence: int | None = None
    guts: int | None = None
    magic_resistance: int | None = None

    @property
    def alive(self) -> bool:
        return self.hp > 0


@dataclass(frozen=True)
class InventoryItem:
    slot: int
    item_id: int
    list_type: str
    name: str
    quantity: int


@dataclass(frozen=True)
class GameState:
    map_id: int
    map_name: str
    previous_map_id: int
    zone_id: int | None
    zone_name: str | None
    x: int
    y: int
    direction: str
    direction_raw: int
    movement_state: int
    blocked_direction: str | None
    blocked_raw: int
    map_context: int
    exploration_mode: int
    battle_mode: int
    dialog_active: bool
    gold: int
    event_flags: str
    scenario_flags: str
    dungeon_flags: str
    transport_flag: int
    party_slots: tuple[int, ...]
    party: tuple[Combatant, ...]
    enemies: tuple[Combatant, ...]
    inventory: tuple[InventoryItem, ...]
    progression_flags: tuple[str, ...]

    @property
    def in_battle(self) -> bool:
        return self.battle_mode != 0

    @property
    def mode(self) -> str:
        if self.in_battle:
            return "battle"
        if self.dialog_active:
            return "dialog"
        # The overworld uses exploration_mode=00 during ordinary player
        # control; towns/dungeons use 01.  Battle/dialog gates above prevent
        # this map-specific rule from mistaking their UI for movement.
        if self.exploration_mode == 1 or self.map_id == 0:
            return "exploration"
        return "other"

    def compact(self) -> dict:
        result = asdict(self)
        result["mode"] = self.mode
        result["in_battle"] = self.in_battle
        inventory_progression = [
            item.name
            for item in self.inventory
            if any(
                token in item.name.casefold()
                for token in (
                    "key", "bomb", "hammer", "hook", "arrow", "engine", "jade",
                    "cloud", "heart", "flower", "magma", "truth", "sword",
                )
            )
        ]
        result["progression_items"] = sorted(set(inventory_progression) | set(self.progression_flags))
        return result

    @classmethod
    def from_wram(cls, data: bytes) -> "GameState":
        if len(data) != 0x20000:
            raise ValueError(f"Expected 131072 WRAM bytes, got {len(data)}")
        map_id = data[0x05AC]
        battle_mode = data[0x09AA]
        zone = zone_for_map(map_id)
        party_slots = tuple(value for value in data[0x0A7B:0x0A7F] if value < len(CHARACTER_NAMES))
        party = []
        for slot, identity in enumerate(party_slots):
            base = CHARACTER_BASE + identity * CHARACTER_STRIDE
            party.append(
                Combatant(
                    slot=slot,
                    name=CHARACTER_NAMES[identity],
                    identity=identity,
                    level=data[base + 0x11],
                    status=data[base + 0x12],
                    hp=u16(data, base + 0x14),
                    mp=u16(data, base + 0x16),
                    max_hp=u16(data, base + 0x28),
                    max_mp=u16(data, base + 0x2A),
                    ip=data[base + 0xBF],
                    attack=u16(data, base + 0x2C),
                    defense=u16(data, base + 0x2E),
                    strength=u16(data, base + 0x30),
                    agility=u16(data, base + 0x32),
                    intelligence=u16(data, base + 0x34),
                    guts=u16(data, base + 0x36),
                    magic_resistance=u16(data, base + 0x38),
                )
            )
        enemies = []
        # Enemy structs deliberately remain stale after escape/return.  They are
        # authoritative only while the independently confirmed battle flag is set.
        for slot in range(6) if battle_mode else range(0):
            base = ENEMY_BASE + slot * ENEMY_STRIDE
            hp = u16(data, base + 0x14)
            raw_name = data[base + 0x03:base + 0x10]
            name = raw_name.split(b"\0", 1)[0].decode("ascii", errors="replace").strip()
            identity = data[base + 0x53]
            if not name and not identity:
                continue
            enemies.append(
                Combatant(
                    slot=slot,
                    name=name or f"Enemy_{identity:02X}",
                    identity=identity,
                    level=data[base + 0x11],
                    status=data[base + 0x12],
                    hp=hp,
                    mp=u16(data, base + 0x16),
                    max_hp=u16(data, base + 0x28),
                    max_mp=u16(data, base + 0x2A),
                    attack=u16(data, base + 0x2C),
                    defense=u16(data, base + 0x2E),
                    strength=u16(data, base + 0x30),
                    agility=u16(data, base + 0x32),
                    intelligence=u16(data, base + 0x34),
                    guts=u16(data, base + 0x36),
                    magic_resistance=u16(data, base + 0x38),
                )
            )
        inventory = []
        for slot, offset in enumerate(range(0x0A8D, 0x0B4D, 2)):
            item_id = data[offset]
            quantity_byte = data[offset + 1]
            if quantity_byte == 0:
                continue
            list_type = "Odd" if quantity_byte & 1 else "Even"
            quantity = quantity_byte // 2
            inventory.append(
                InventoryItem(
                    slot=slot,
                    item_id=item_id,
                    list_type=list_type.casefold(),
                    name=ITEM_DB.get(f"{item_id:02X}_{list_type}", f"Unknown_{item_id:02X}_{list_type}"),
                    quantity=quantity,
                )
            )
        scenario_value = int.from_bytes(data[0x091E:0x0921], "big")
        progression_flags = tuple(
            name for name, mask in PROGRESSION_FLAG_MASKS.items() if mask and scenario_value & mask == mask
        )
        direction_raw = data[0x0692]
        blocked_raw = data[0x1272]
        return cls(
            map_id=map_id,
            map_name=MAP_DB.get(f"{map_id:02X}", f"Unknown Map ({map_id:02X})"),
            previous_map_id=data[0x05AE],
            zone_id=zone["id"] if zone else None,
            zone_name=zone["name"] if zone else None,
            x=data[0x06BA],
            y=data[0x06E2],
            direction=DIRECTION_NAMES.get(direction_raw, f"unknown_{direction_raw:02X}"),
            direction_raw=direction_raw,
            movement_state=data[0x066A],
            blocked_direction=BLOCKED_NAMES.get(blocked_raw),
            blocked_raw=blocked_raw,
            map_context=data[0x09A7],
            exploration_mode=data[0x09A9],
            battle_mode=battle_mode,
            dialog_active=bool(data[0x099B] or data[0x099C]),
            gold=u16(data, 0x0A8A),
            event_flags=data[0x077E:0x079E].hex(),
            scenario_flags=data[0x091E:0x0921].hex(),
            dungeon_flags=data[0x0782:0x078C].hex(),
            transport_flag=data[0x09E1],
            party_slots=party_slots,
            party=tuple(party),
            enemies=tuple(enemies),
            inventory=tuple(inventory),
            progression_flags=progression_flags,
        )
