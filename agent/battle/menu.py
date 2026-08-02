"""Decode only confirmed battle menus and expose verified legal choices."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from agent.battle.policy import BattleOption
from agent.battle.state import BattleState
from agent.game_state import CHARACTER_BASE, CHARACTER_STRIDE


ROOT = Path(__file__).resolve().parents[2]
SPELLS = json.loads((ROOT / "data/spells_info.json").read_text(encoding="utf-8"))
COMBAT_ITEMS = json.loads((ROOT / "data/combat_items.json").read_text(encoding="utf-8"))
IP_SKILLS = json.loads((ROOT / "data/ip_skills.json").read_text(encoding="utf-8"))
IP_BY_NAME = {
    "".join(char for char in entry["name"].casefold() if char.isalnum()): entry
    for entry in IP_SKILLS
}


class BattleMenuType(str, Enum):
    MAGIC = "magic"
    ITEM = "item"
    IP = "ip"
    TARGET = "target"
    UNKNOWN = "unknown"


def _printable(value: int) -> str:
    return chr(value) if 32 <= value <= 126 else " "


def _interleaved(raw: bytes, parity: int) -> str:
    return "".join(_printable(value) for value in raw[parity::2])


def _target_semantics(description: str) -> tuple[str, bool]:
    text = description.casefold()
    ally_words = ("restores", "revive", "cures", "heals", "increases", "repels")
    enemy_words = ("attack", "damage", "foe", "enemy", "inflicts", "annihilation", "decreases")
    side = "ally" if any(word in text for word in ally_words) else "enemy" if any(
        word in text for word in enemy_words
    ) else "unknown"
    return side, "all" in text


class BattleMenuReader:
    PROMPT_START = 0x3040
    PROMPT_LENGTH = 0x80

    @classmethod
    def prompt(cls, data: bytes) -> str:
        return " ".join(
            _interleaved(data[cls.PROMPT_START:cls.PROMPT_START + cls.PROMPT_LENGTH], 0).split()
        )

    @classmethod
    def menu_type(cls, state: BattleState, data: bytes) -> BattleMenuType:
        if state.target_flags & 0x80:
            return BattleMenuType.TARGET
        prompt = cls.prompt(data).casefold()
        if "choose a spell" in prompt:
            return BattleMenuType.MAGIC
        if "choose an item" in prompt:
            return BattleMenuType.ITEM
        if "choose equipment" in prompt:
            return BattleMenuType.IP
        return BattleMenuType.UNKNOWN

    @staticmethod
    def command_options(state: BattleState, data: bytes, actor_slot: int) -> list[BattleOption]:
        if not 0 <= actor_slot < len(state.game.party):
            return []
        actor = state.game.party[actor_slot]
        options = [
            BattleOption("attack", actor_slot, "Attack", 0, option_id=f"command:{actor_slot}:attack"),
            BattleOption("defend", actor_slot, "Defend", 0, option_id=f"command:{actor_slot}:defend"),
        ]
        spell_start = CHARACTER_BASE + actor.identity * CHARACTER_STRIDE + 0x99
        learned = any(
            value != 0xFF and SPELLS.get(f"{value:02X}", {}).get("combat", False)
            for value in data[spell_start:spell_start + 36]
        )
        if actor.max_mp > 0 and learned:
            options.append(BattleOption("magic_menu", actor_slot, "Magic", 0, option_id=f"command:{actor_slot}:magic"))
        if any(
            f"{item.item_id:02X}" in COMBAT_ITEMS.get(item.list_type, {})
            for item in state.game.inventory
        ):
            options.append(BattleOption("item_menu", actor_slot, "Item", 0, option_id=f"command:{actor_slot}:item"))
        if (actor.ip or 0) > 0:
            options.append(BattleOption("ip_menu", actor_slot, "IP", 0, option_id=f"command:{actor_slot}:ip"))
        return options

    @staticmethod
    def visible_magic(data: bytes, actor_slot: int, actor_identity: int) -> list[BattleOption]:
        first = data[0x0011]
        selected = data[0x0012]
        spell_base = CHARACTER_BASE + actor_identity * CHARACTER_STRIDE + 0x99
        options = []
        for row in range(6):
            for column, offset in ((0, 0), (1, 0x1C)):
                index = first + row * 2 + column
                if index >= 36:
                    continue
                spell_id = data[spell_base + index]
                if spell_id == 0xFF:
                    continue
                start = 0x3146 + row * 0x80 + offset
                raw = data[start:start + 0x1C]
                text = _interleaved(raw, 0).strip()
                if ":" not in text:
                    continue
                name, raw_cost = text.rsplit(":", 1)
                try:
                    cost = int(raw_cost.strip())
                except ValueError:
                    continue
                meta = SPELLS.get(f"{spell_id:02X}", {})
                description = str(meta.get("description", ""))
                side, all_targets = _target_semantics(description)
                options.append(BattleOption(
                    "spell",
                    actor_slot,
                    name.strip(),
                    0,
                    usable=raw[1] == 0x20,
                    mp_cost=cost,
                    all_targets=all_targets,
                    supports_group_toggle=side in {"ally", "enemy"},
                    option_id=f"spell:{actor_slot}:{index}:{spell_id:02X}",
                    menu_index=index,
                    ability_id=spell_id,
                    description=description,
                    target_side=side,
                ))
        return options

    @staticmethod
    def visible_items(data: bytes, actor_slot: int) -> list[BattleOption]:
        first_byte = data[0x0011]
        options = []
        for row in range(6):
            byte_offset = first_byte + row * 2
            if byte_offset >= 0xC0:
                continue
            storage_slot = byte_offset // 2
            item_id = data[0x0A8D + byte_offset]
            quantity_byte = data[0x0A8E + byte_offset]
            start = 0x3147 + row * 0x80
            raw = data[start:start + 0x40]
            text = _interleaved(raw, 1).strip()
            if not text or ":" not in text or quantity_byte == 0:
                continue
            name, _ = text.rsplit(":", 1)
            list_type = "odd" if quantity_byte & 1 else "even"
            meta = COMBAT_ITEMS.get(list_type, {}).get(f"{item_id:02X}", {})
            description = str(meta.get("desc", ""))
            side, inferred_all = _target_semantics(description)
            all_targets = str(meta.get("target", "")).casefold() == "all" or inferred_all
            options.append(BattleOption(
                "item",
                actor_slot,
                name.strip(),
                0,
                usable=raw[2] == 0x20,
                consumes_item=True,
                all_targets=all_targets,
                option_id=f"item:{actor_slot}:{storage_slot}:{item_id:02X}:{list_type}",
                menu_index=byte_offset,
                storage_slot=storage_slot,
                ability_id=item_id,
                description=description,
                target_side=side,
            ))
        return options

    @staticmethod
    def visible_ip(data: bytes, actor_slot: int) -> list[BattleOption]:
        selected = data[0x0014]
        options = []
        for row in range(6):
            start = 0x3147 + row * 0x80
            raw = data[start:start + 0x40]
            rendered = _interleaved(raw, 1).rstrip()
            gear = rendered[:13].strip()
            name = rendered[13:].strip()
            if not gear or not name:
                continue
            normalized = "".join(char for char in name.casefold() if char.isalnum())
            meta = IP_BY_NAME.get(normalized, {})
            description = str(meta.get("description", ""))
            side, all_targets = _target_semantics(description)
            equipment_id = int.from_bytes(data[0x1357 + row * 2:0x1359 + row * 2], "little")
            options.append(BattleOption(
                "ip",
                actor_slot,
                name,
                0,
                usable=raw[2] == 0x20,
                ip_cost=int(meta.get("cost", 0) or 0),
                element=",".join(meta.get("elements", [])) or None,
                all_targets=all_targets,
                option_id=f"ip:{actor_slot}:{row}:{equipment_id:04X}",
                menu_index=row,
                ability_id=equipment_id,
                description=description,
                target_side=side,
            ))
        return options
