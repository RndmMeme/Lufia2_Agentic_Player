#!/usr/bin/env python3
"""Build a complete, provenance-preserving Lufia II WRAM truth set.

The historic project data mixes ROM offsets, Snes9x process addresses,
Snes9x host-mirror offsets and real SNES WRAM offsets.  This script never
silently treats one namespace as another.  It emits:

* one normalized semantic record for every field in data/ram_map.json;
* every address-like raw claim from all selected legacy sources;
* explicit evidence/status for the Mesen addresses tested against the game UI.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LEGACY_DELTA = 0x2314
ROM_SHA1 = "1D0A95DDCCEB399E8FEC51BA5CBB6A6C5D30E0E0"

JSON_SOURCES = [
    "data/emulator_addresses.json",
    "data/shop_addresses.json",
    "data/dungeon_flags_snes9x.json",
    "data/dungeon_flags_snes9x-nwa.json",
    "data/ram_map.json",
    "data/ram_mappings/ram_static_offsets.json",
    "data/ram_mappings/ram_volatile_stats.json",
    "data/ram_mappings/rom_pointers.json",
]
TEXT_SOURCES = [
    "docs/lufia2_wram_checklist_merged_update_v5.txt",
    "emulator/csharp_helper/Core/Lufia2MemoryMap.cs",
    "emulator/csharp_helper/Core/DataReaders.cs",
]

HEX_RE = re.compile(r"(?i)(?:0x)?[0-9a-f]{4,16}")
BUS_RE = re.compile(r"(?i)7[ef]:[0-9a-f]{4}")

DIRECT_MESEN_FIELDS = {
    "EventFlagsStart",
    "EventFlagsEnd",
    "EquipmentInspectNameBuffer",
    "EquipmentInspectDescriptionStart",
    "EquipmentInspectDescriptionEnd",
    "EquipmentInspectMetaStart",
    "EquipmentInspectMetaEnd",
    "EquipmentReplaceListStart",
    "EquipmentReplaceListEnd",
}

CONFIRMED_FIELDS = {
    "Gold",
    "PartySlots",
    "InventoryStart",
    "InventoryEnd",
    "CapsuleSlots",
    "FacingDirectionStateMirror",
    "DungeonAxisMirrorX",
    "DungeonAxisMirrorY",
    "DungeonXHigh",
    "DungeonYHigh",
    "TownX",
    "TownY",
    "CurrentMap",
}
OBSERVED_FIELDS = {
    "ScenarioStart",
    "ScenarioEnd",
    "DungeonFlagStart",
    "DungeonFlagEnd",
    "TransportFlag",
    "ShipXFast",
    "ShipXSlow",
    "ShipYFast",
    "ShipYSlow",
    "WalkXFast",
    "WalkXSlow",
    "WalkYFast",
    "WalkYSlow",
    "MapContextFlag",
    "ExplorationModeFlag",
    "BattleModeFlag",
}
UNRELIABLE_FIELDS = {"DungeonBlocking"}
MESEN_OVERRIDES = {
    "SelectedItemPrice": [0x0B89],
    "ShopCursorPosition": [0x1574],
}
RESULT_OVERRIDES = {
    "BattleResultExpTextStart": (
        [0x1605],
        "Visible EXP 2689 matched uint16; this is numeric reward data, not text.",
    ),
    "BattleResultGoldTextStart": (
        [0x1608],
        "Visible gold 4140 matched uint16; this is numeric reward data, not text.",
    ),
    "EquipmentRenderPaneStart": (
        [0x30CA],
        "Live IP menu render buffer; prompt and all six rows were decoded from Mesen WRAM.",
    ),
    "EquipmentRenderPaneEnd": (
        [0x3447],
        "Corrected live end includes the sixth equipment/IP row, which the legacy boundary omitted.",
    ),
    "EquipmentPromptPaneStart": (
        [0x3046],
        "Interleaved ASCII decoded to the visible text 'Please choose equipment.'.",
    ),
    "EquipmentFirstEntryStart": (
        [0x3147],
        "First live equipment row buffer; visible text starts at the following byte.",
    ),
}


def parse_hex(value: str) -> int:
    return int(value, 16)


def bus(offset: int) -> str:
    if not 0 <= offset < 0x20000:
        return ""
    if offset < 0x10000:
        return f"7E:{offset:04X}"
    return f"7F:{offset - 0x10000:04X}"


def json_walk(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from json_walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from json_walk(child, f"{path}[{index}]")
    else:
        yield path, value


def classify_raw(source: str, path: str, token: str, context: str) -> str:
    lower_source = source.casefold()
    lower_path = path.casefold()
    lower_context = context.casefold()
    normalized = token.casefold()

    if "shop_addresses" in lower_source or "rom_pointers" in lower_source:
        return "rom_offset"
    if any(word in lower_path for word in ("flag", "binary", "status_values")):
        return "semantic_value"
    if "7e:" in normalized or "7f:" in normalized:
        return "snes_bus_wram"
    if "[rom]" in lower_context or any(
        word in lower_path
        for word in (
            "rom_",
            "rom.",
            "offset",
            "table",
            "spoiler",
            "sprite",
            "shopdirectory",
            "itemtable",
            "spellpointer",
        )
    ):
        return "rom_or_file_offset"

    digits = normalized.replace("0x", "").replace(":", "")
    try:
        number = int(digits, 16)
    except ValueError:
        return "unknown"
    if number >= 0x100000:
        return "emulator_process_address"
    if number < 0x20000:
        return "ambiguous_relative_or_wram"
    return "rom_or_process_offset"


def raw_claims() -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    claims: list[dict[str, Any]] = []
    coverage: dict[str, dict[str, int]] = {}

    for relative in JSON_SOURCES:
        path = ROOT / relative
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        count = 0
        classes: Counter[str] = Counter()
        for json_path, value in json_walk(data):
            if not isinstance(value, str):
                continue
            for match in HEX_RE.finditer(value):
                token = match.group(0)
                kind = classify_raw(relative, json_path, token, value)
                claims.append(
                    {
                        "source": relative,
                        "location": json_path,
                        "token": token,
                        "namespace": kind,
                        "context": value,
                    }
                )
                count += 1
                classes[kind] += 1
        coverage[relative] = {"claims": count, **dict(classes)}

    for relative in TEXT_SOURCES:
        path = ROOT / relative
        count = 0
        classes: Counter[str] = Counter()
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1
        ):
            matches = list(BUS_RE.finditer(line)) + list(HEX_RE.finditer(line))
            occupied: list[tuple[int, int]] = []
            for match in sorted(matches, key=lambda item: item.start()):
                span = match.span()
                if any(span[0] >= old[0] and span[1] <= old[1] for old in occupied):
                    continue
                occupied.append(span)
                token = match.group(0)
                kind = classify_raw(relative, f"line:{line_number}", token, line)
                claims.append(
                    {
                        "source": relative,
                        "location": f"line:{line_number}",
                        "token": token,
                        "namespace": kind,
                        "context": line.strip(),
                    }
                )
                count += 1
                classes[kind] += 1
        coverage[relative] = {"claims": count, **dict(classes)}
    return claims, coverage


def normalize_offset_field(name: str, value: str | list[str]) -> dict[str, Any]:
    values = value if isinstance(value, list) else [value]
    legacy = [parse_hex(item) for item in values]

    if name in RESULT_OVERRIDES:
        mesen, rationale = RESULT_OVERRIDES[name]
        namespace = "legacy_snes9x_host_mirror"
        status = "confirmed"
    elif name in MESEN_OVERRIDES:
        mesen = MESEN_OVERRIDES[name]
        namespace = "legacy_snes9x_host_mirror"
        status = "confirmed"
        rationale = (
            "Three visible Dankirk shop rows matched atomically; this field does "
            "not follow the general legacy helper delta."
        )
    elif name in DIRECT_MESEN_FIELDS:
        mesen = legacy
        namespace = "mesen_snes_work_ram"
        status = "observed"
        rationale = "Source field was added from direct Mesen/UI-buffer observation."
    elif name in UNRELIABLE_FIELDS:
        mesen = [item - LEGACY_DELTA for item in legacy if item >= LEGACY_DELTA]
        namespace = "legacy_snes9x_host_mirror"
        status = "unreliable"
        rationale = "Existing candidate contradicted live behavior or documented value domain."
    elif name in CONFIRMED_FIELDS or name == "CurrentToolName":
        mesen = [item - LEGACY_DELTA for item in legacy]
        namespace = "legacy_snes9x_host_mirror"
        status = "confirmed"
        rationale = "Controlled Mesen transition and/or exact visible UI value."
    elif name in OBSERVED_FIELDS:
        mesen = [item - LEGACY_DELTA for item in legacy]
        namespace = "legacy_snes9x_host_mirror"
        status = "observed"
        rationale = "Corrected block location is plausible; semantic state transition remains pending."
    elif name.startswith("EventFlags"):
        mesen = legacy
        namespace = "mesen_snes_work_ram"
        status = "observed"
        rationale = "Low WRAM event region is not part of the translated host-mirror family."
    else:
        mesen = [item - LEGACY_DELTA for item in legacy if item >= LEGACY_DELTA]
        namespace = "legacy_snes9x_host_mirror"
        status = "candidate"
        rationale = "Mechanical family translation only; not promoted without semantic evidence."

    return {
        "name": name,
        "source": "data/ram_map.json",
        "source_namespace": namespace,
        "legacy_values": [f"0x{item:05X}" for item in legacy],
        "mesen_offsets": [f"0x{item:05X}" for item in mesen],
        "mesen_bus": [bus(item) for item in mesen],
        "status": status,
        "rationale": rationale,
    }


def semantic_records() -> list[dict[str, Any]]:
    ram_map = json.loads((ROOT / "data/ram_map.json").read_text(encoding="utf-8"))
    records = [
        normalize_offset_field(name, value)
        for name, value in ram_map["offsets"].items()
    ]

    for character, fields in ram_map["characters"]["individual_offsets"].items():
        for field, value in fields.items():
            legacy = parse_hex(value)
            actual = legacy - LEGACY_DELTA
            status = "confirmed_structure"
            rationale = (
                "0xBE stride and corrected block layout confirmed. Active party values "
                "were checked against visible status screens; inactive blocks have name anchors."
            )
            records.append(
                {
                    "name": f"Character.{character}.{field}",
                    "source": "data/ram_map.json",
                    "source_namespace": "legacy_snes9x_host_mirror",
                    "legacy_values": [f"0x{legacy:05X}"],
                    "mesen_offsets": [f"0x{actual:05X}"],
                    "mesen_bus": [bus(actual)],
                    "status": status,
                    "rationale": rationale,
                }
            )

    for enemy, value in ram_map["enemies"]["slot_offsets"].items():
        legacy = parse_hex(value)
        actual = legacy - LEGACY_DELTA
        records.append(
            {
                "name": f"Enemy.{enemy}.currentHpAnchor",
                "source": "data/ram_map.json",
                "source_namespace": "legacy_snes9x_host_mirror",
                "legacy_values": [f"0x{legacy:05X}"],
                "mesen_offsets": [f"0x{actual:05X}"],
                "mesen_bus": [bus(actual)],
                "status": "confirmed",
                "rationale": (
                    "This legacy-derived address is CurrentHP, not the full struct base. "
                    "Six-slot 0xBE layout confirmed; three Garbost had 637 HP."
                ),
            }
        )

    records.extend(
        [
            {
                "name": "PreviousMap",
                "source": "Mesen live Overworld/Secret Skills Cave transition",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x005AE"],
                "mesen_bus": ["7E:05AE"],
                "status": "confirmed",
                "rationale": (
                    "uint8 origin map: Overworld held 05 after leaving Secret "
                    "Skills Cave; the cave held 00 after entry from Overworld."
                ),
            },
            {
                "name": "EnemyCombatStatStruct",
                "source": "Mesen live enemy-struct audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": ["Old enemy anchors were CurrentHP, not struct bases"],
                "mesen_offsets": [
                    "0x01618 + slot*0xBE",
                    "Name +0x03, 13 ASCII bytes",
                    "Enemy ID +0x53",
                    "Level +0x11",
                    "Status +0x12",
                    "CurrentHP +0x14",
                    "CurrentMP +0x16",
                    "MaxHP +0x28",
                    "MaxMP +0x2A",
                    "ATP +0x2C",
                    "DFP +0x2E",
                    "STR +0x30",
                    "AGL +0x32",
                    "INT +0x34",
                    "GUT +0x36",
                    "MGR +0x38",
                ],
                "mesen_bus": ["7E:1618 + slot*0xBE"],
                "status": "confirmed",
                "rationale": (
                    "Three identical Garbost blocks matched the character combat-stat "
                    "layout exactly. All three had level 50; CurrentHP changed "
                    "637->0/336 while MaxHP stayed 637; the defeated slot's status "
                    "changed 00->04. Freeze ball changed an undamaged target's "
                    "status 00->08, confirming Paralyze. A second species exposed "
                    "the inline name Ramia and different stats at the same offsets. "
                    "Live IDs 54 Garbost and 3B Ramia matched Abyssonym's complete "
                    "monster table exactly."
                ),
            },
            {
                "name": "BattlePartyCommandSlots",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": ["Character base + 0x13 (contradicted)"],
                "mesen_offsets": ["0x1F560 + slot*0x0C + 0x04"],
                "mesen_bus": ["7F:F564", "7F:F570", "7F:F57C", "7F:F588"],
                "status": "confirmed",
                "rationale": "Mirrored Attack/Defend tests proved 01/04 and 0x0C slot stride.",
            },
            {
                "name": "BattlePartyStoredTargetMask",
                "source": "Mesen live targeting audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x1F560 + slot*0x0C + 0x00"],
                "mesen_bus": ["7F:F560", "7F:F56C", "7F:F578", "7F:F584"],
                "status": "confirmed",
                "rationale": (
                    "Party targets stored 01/02/04/08 and all four 0F. Enemy targets "
                    "set flag 80: live single targets 81/82/84 and all three 87. "
                    "Enemy bits 08/10/20 and all-six BF are structurally derived, "
                    "not yet observed in a rare six-enemy encounter."
                ),
            },
            {
                "name": "BattleActiveTargetIndex",
                "source": "Mesen live targeting audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x00026"],
                "mesen_bus": ["7E:0026"],
                "status": "confirmed",
                "rationale": (
                    "Manual left/middle/right selection produced zero-based 00/01/02. "
                    "This is the fixed temporary cursor only and cannot distinguish "
                    "R/all-target mode; read the stored command mask after confirmation."
                ),
            },
            {
                "name": "BattlePartyActorMask",
                "source": "Mesen live targeting audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x1F560 + slot*0x0C + 0x0A"],
                "mesen_bus": ["7F:F56A", "7F:F576", "7F:F582", "7F:F58E"],
                "status": "confirmed",
                "rationale": (
                    "The value stayed 04 for Arty while targets changed from 82 to 84; "
                    "it is an actor mask, not the target or target companion."
                ),
            },
            {
                "name": "BattleInitiativeQueue",
                "source": "Mesen passive Ramia round audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": [
                    "0x01B8C + index*0x03",
                    "Actor mask +0x00",
                    "Initiative uint16 LE +0x01",
                ],
                "mesen_bus": ["7E:1B8C"],
                "status": "confirmed",
                "rationale": (
                    "Eight materialized entries executed in exact descending order: "
                    "266,187,140,133,108,45,45,43. Maximum actor capacity is 11 "
                    "(four humans, capsule and six enemies)."
                ),
            },
            {
                "name": "BattleActiveAction",
                "source": "Mesen passive Ramia round audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": [
                    "0x1F44E",
                    "Actor mask +0x00",
                    "Target mask +0x02",
                    "Command +0x06",
                    "Action ID +0x0A",
                ],
                "mesen_bus": ["7F:F44E"],
                "status": "confirmed",
                "rationale": (
                    "The active actor sequence matched the initiative queue exactly. "
                    "Ramia targets 08/10/08 identified Tia/capsule/Tia; Tia HP fell "
                    "619->596->571 on the two target-08 actions. The randomized ROM "
                    "action-name pointer table maps hex ID 16 to Tail attack "
                    "(15=Miracle voice, 17=Picking)."
                ),
            },
            {
                "name": "BattleGroupMenuSelection",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x00B4E"],
                "mesen_bus": ["7E:0B4E"],
                "status": "confirmed",
                "rationale": "Held cursor states matched Fight 09, Trade 0A and Escape 0B.",
            },
            {
                "name": "BattleFormation",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x0153D", "0x0153E", "0x0153F", "0x01540"],
                "mesen_bus": ["7E:153D", "7E:153E", "7E:153F", "7E:1540"],
                "status": "confirmed",
                "rationale": "Guy/Arty trade changed 02 03 01 04 to 03 02 01 04 without changing canonical party.",
            },
            {
                "name": "BattleRewardValidity",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": ["0x0541C", "0x05744"],
                "mesen_offsets": ["0x01605", "0x01608"],
                "mesen_bus": ["7E:1605", "7E:1608"],
                "status": "confirmed",
                "rationale": "EXP 2689 and gold 4140 matched; old text buffers were unchanged and rewards remain stale after return.",
            },
            {
                "name": "BattleIpMenuCursor",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x00014", "0x00101"],
                "mesen_bus": ["7E:0014", "7E:0101"],
                "status": "confirmed",
                "rationale": "Six manually positioned rows produced index 00-05 and Y values 20,2C,38,44,50,5C.",
            },
            {
                "name": "BattleIpEquipmentList",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x01357-0x01362"],
                "mesen_bus": ["7E:1357-1362"],
                "status": "confirmed",
                "rationale": "The battle menu copied all six equipped item IDs here in equipment-slot order.",
            },
            {
                "name": "BattleIpRenderedRows",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": ["0x0545B first row; old end 0x056CE omitted row six"],
                "mesen_offsets": ["0x03147 + row*0x80", "IP name at row + 0x1B"],
                "mesen_bus": ["7E:3147 + row*0x80"],
                "status": "confirmed",
                "rationale": "Six screenshots matched six interleaved-ASCII rows. WRAM stores item IDs and rendered names, not a separate six-entry IP-ID list.",
            },
            {
                "name": "BattleIpAvailability",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["rendered row + 0x02"],
                "mesen_bus": ["7E:3149 + row*0x80"],
                "status": "confirmed",
                "rationale": "Attribute 20 marked costs <= Guy's 96 IP usable; 24 marked costs above 96 unusable. Equality at 96 was usable.",
            },
            {
                "name": "BattleIpConsumption",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["Character base + 0xBF; Guy 0x00DE5"],
                "mesen_bus": ["7E:0DE5"],
                "status": "confirmed",
                "rationale": "Sleep Stinger cost 96: selection and target confirmation kept 96; actual execution changed 96 to 0.",
            },
            {
                "name": "BattleMagicMenuCursor",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x00011-0x00014", "0x00100-0x00101"],
                "mesen_bus": ["7E:0011-0014", "7E:0100-0101"],
                "status": "confirmed",
                "rationale": "True top, horizontal, vertical, first empty and true 36-slot end states matched.",
            },
            {
                "name": "BattleMagicRenderedRows",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x03146 + row*0x80"],
                "mesen_bus": ["7E:3146 + row*0x80"],
                "status": "confirmed",
                "rationale": "Two-column scrolling pane exposes randomized live costs and attribute 20 usable / 24 disabled.",
            },
            {
                "name": "CharacterSpellSlots",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": ["Character base + 0x99"],
                "mesen_offsets": ["Character base + 0x99, 36 bytes"],
                "mesen_bus": ["Guy example 7E:0DBF-0DE2"],
                "status": "confirmed",
                "rationale": "Battle and field menu share the same fixed 36-slot order; FF slots are empty but navigable.",
            },
            {
                "name": "BattleMagicSelectionAndConsumption",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x1F564 command", "0x1F566 spell ID", "Character current MP"],
                "mesen_bus": ["7F:F564", "7F:F566", "Guy 7E:0D3C-0D3D"],
                "status": "confirmed",
                "rationale": "Fireball produced command 02, spell ID 04; MP stayed 471 through selection then fell to 465 on execution, matching live cost 6.",
            },
            {
                "name": "BattleItemMenuCursor",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x00011-0x00014", "0x00100-0x00101"],
                "mesen_bus": ["7E:0011-0014", "7E:0100-0101"],
                "status": "confirmed",
                "rationale": "Empty slot 1, occupied slots 2/3 and true slot 96 end matched fixed raw inventory positions.",
            },
            {
                "name": "BattleItemRenderedRows",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x03147 + row*0x80"],
                "mesen_bus": ["7E:3147 + row*0x80"],
                "status": "confirmed",
                "rationale": "Rows preserve empty inventory slots; attribute 20 means battle-usable and 24 means visible but disabled.",
            },
            {
                "name": "InventorySlotStructure",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": ["0x02DA1-0x02E60 inclusive"],
                "mesen_offsets": ["0x00A8D-0x00B4C inclusive"],
                "mesen_bus": ["7E:0A8D-0B4C"],
                "status": "confirmed",
                "rationale": "96 fixed two-byte slots require 0xC0 bytes; old helper length 0xBF omitted slot 96's second byte.",
            },
            {
                "name": "BattleItemSelectionAndConsumption",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x1F564 command", "0x1F566-0x1F567 raw item pair", "inventory slot"],
                "mesen_bus": ["7F:F564", "7F:F566-F567", "Charred example 7E:0A8F-0A90"],
                "status": "confirmed",
                "rationale": "Charred Newt command 03 stored 01 02. Selection transition temporarily cleared the slot; final empty slot plus Guy MP 465 to 470 proved execution.",
            },
            {
                "name": "DungeonActorLayout",
                "source": "Mesen controlled movement audit plus ROM dispatch inspection",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": [
                    "Sprite 0x005D2 + slot",
                    "Movement state 0x0066A + slot",
                    "Direction 0x00692 + slot",
                    "Tile X 0x006BA + slot",
                    "Tile Y 0x006E2 + slot",
                    "Movement mode 0x0070A + slot",
                    "Facing 0x1E466 + slot",
                ],
                "mesen_bus": [
                    "7E:05D2 + slot",
                    "7E:066A + slot",
                    "7E:0692 + slot",
                    "7E:06BA + slot",
                    "7E:06E2 + slot",
                    "7E:070A + slot",
                    "7F:E466 + slot",
                ],
                "status": "confirmed",
                "rationale": (
                    "Forty slots 00-27; FF is empty. Controlled up/down/left/right "
                    "changed only the matching tile axis. Movement-state bit 0 "
                    "distinguishes moving from idle. Stable direction uses "
                    "00 south, 02 west, 04 north, 06 east; facing uses low bits 0-3."
                ),
            },
            {
                "name": "DungeonActorMovementMode",
                "source": "Authoritative Terrorwave MonsterMoveObject plus live Mesen",
                "source_namespace": "rom_and_mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x0070A + slot"],
                "mesen_bus": ["7E:070A + slot"],
                "status": "confirmed",
                "rationale": (
                    "For overworld sprites 80-EF, the runtime byte equals ROM "
                    "MonsterMoveObject[SpriteID-80]. All six loaded monster actors "
                    "matched the randomized ROM table."
                ),
            },
            {
                "name": "DungeonBlockedAttempt",
                "source": "Mesen controlled wall collision",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": ["0x03586 old unsupported claim"],
                "mesen_offsets": ["0x01272", "Tile X/Y 0x006BA/0x006E2 + slot"],
                "mesen_bus": [
                    "7E:1272",
                    "7E:06BA/06E2 + slot",
                ],
                "status": "confirmed",
                "rationale": (
                    "A visible south-wall attempt produced FF->01 at 7E:1272 "
                    "with unchanged X/Y. ROM code stores attempted direction on "
                    "collision and resets FF on success: 00 north, 01 south, "
                    "02 west, 03 east. The old 7E:3586 mapping is unsupported."
                ),
            },
            {
                "name": "SelectedDungeonToolCode",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": ["0x02D1A"],
                "mesen_offsets": ["0x00A06", "0x00A07"],
                "mesen_bus": ["7E:0A06", "7E:0A07"],
                "status": "confirmed",
                "rationale": "Bomb selection matched A8 01 and ASCII name Bomb at 7E:0B77.",
            },
            {
                "name": "DungeonToolActionState",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": ["0x02CBC"],
                "mesen_offsets": ["0x009A8"],
                "mesen_bus": ["7E:09A8"],
                "status": "confirmed",
                "rationale": "Bomb lifecycle matched 00 idle, 77 placed, 7F explosion, 00 idle.",
            },
            {
                "name": "NpcDialogIndicator",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": [],
                "mesen_offsets": ["0x0099B", "0x0099C"],
                "mesen_bus": ["7E:099B", "7E:099C"],
                "status": "confirmed",
                "rationale": (
                    "Two NPCs matched 0000 -> 8801 -> 0000; an open shop "
                    "remained 0000."
                ),
            },
            {
                "name": "SaveSelectionCursor",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": ["0xA32454-0xA32455"],
                "mesen_offsets": ["0x00108", "0x00109"],
                "mesen_bus": ["7E:0108", "7E:0109"],
                "status": "confirmed",
                "rationale": "All seven visible cursor positions atomically matched value and companion byte.",
            },
            {
                "name": "NameEntryCursor",
                "source": "Mesen live audit",
                "source_namespace": "mesen_snes_work_ram",
                "legacy_values": ["0xA32414-0xA32415"],
                "mesen_offsets": ["0x00100", "0x00101"],
                "mesen_bus": ["7E:0100", "7E:0101"],
                "status": "partially_confirmed",
                "rationale": "Live candidate; not every name-grid position has been exercised.",
            },
        ]
    )
    return records


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    records = payload["semantic_records"]
    counts = Counter(record["status"] for record in records)
    lines = [
        "# Lufia II WRAM base of truth",
        "",
        f"ROM SHA-1: `{ROM_SHA1}`  ",
        "Live backend: `Mesen 2.1.1 / snesWorkRam / 128 KiB`",
        "",
        "Diese Datei trennt echte Mesen-WRAM-Adressen von historischen "
        "Snes9x-Prozess- und Hostspiegel-Adressen. Ein mechanisch abgeleiteter "
        "Kandidat ist keine Bestätigung.",
        "",
        "## Status",
        "",
    ]
    for status, count in sorted(counts.items()):
        lines.append(f"- `{status}`: {count}")

    lines.extend(
        [
            "",
            "## Semantische Adressen",
            "",
            "| Status | Feld | Legacy | Mesen | Begründung |",
            "|---|---|---|---|---|",
        ]
    )
    for record in records:
        legacy = ", ".join(record["legacy_values"])
        mesen = ", ".join(record["mesen_bus"]) or "—"
        rationale = record["rationale"].replace("|", "/")
        lines.append(
            f"| {record['status']} | {record['name']} | {legacy} | {mesen} | {rationale} |"
        )

    lines.extend(
        [
            "",
            "## Quellenabdeckung",
            "",
            "| Quelle | extrahierte Adressbehauptungen |",
            "|---|---:|",
        ]
    )
    for source, coverage in payload["source_coverage"].items():
        lines.append(f"| `{source}` | {coverage['claims']} |")

    lines.extend(
        [
            "",
            "Die vollständige Rohmatrix mit JSON-Pfad beziehungsweise Zeilennummer "
            "steht in `data/lufia2_wram_base_of_truth.json`. Dadurch geht auch bei "
            "widerlegten oder noch nicht getesteten Altangaben nichts verloren.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    claims, coverage = raw_claims()
    records = semantic_records()
    payload = {
        "schema_version": 1,
        "rom": {
            "sha1": ROM_SHA1,
            "randomized": True,
            "address_layout": "unchanged by randomizer",
        },
        "emulator": {
            "name": "Mesen",
            "version": "2.1.1",
            "memory_type": "snesWorkRam",
            "size": 0x20000,
        },
        "legacy_helper_delta": "0x2314",
        "status_meanings": {
            "confirmed": "Exact visible value or controlled state transition.",
            "confirmed_structure": "Layout/stride proven; not every saved value independently changed.",
            "observed": "Plausible live value without the required semantic transition.",
            "candidate": "Mechanically derived only.",
            "unreliable": "Contradicted live behavior or documented value domain.",
            "requires_battle": "Needs a live battle state.",
            "partially_confirmed": "Some but not all enumerated states were exercised.",
        },
        "semantic_records": records,
        "source_coverage": coverage,
        "raw_claims": claims,
    }
    json_path = ROOT / "data/lufia2_wram_base_of_truth.json"
    md_path = ROOT / "docs/lufia2_wram_base_of_truth.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(payload, md_path)
    print(f"{len(records)} semantic records")
    print(f"{len(claims)} raw address claims")
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
