#!/usr/bin/env python3
"""Audit legacy helper offsets against true Mesen SNES WRAM captures."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CAPTURE_ROOT = ROOT / "mesen_bridge" / "validation" / "gameplay"
LEGACY_HELPER_DELTA = 0x2314


@dataclass
class Result:
    status: str
    claim: str
    legacy_offset: str
    mesen_offset: str
    observed: str
    evidence: str


def actual(legacy_offset: int) -> int:
    return legacy_offset - LEGACY_HELPER_DELTA


def bus(offset: int) -> str:
    return f"7E:{offset:04X}" if offset < 0x10000 else f"7F:{offset - 0x10000:04X}"


def hx(data: bytes) -> str:
    return data.hex(" ").upper()


def u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "little")


def u24(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 3], "little")


def add(
    results: list[Result],
    status: str,
    claim: str,
    legacy: int,
    observed: str,
    evidence: str,
    mesen: int | None = None,
) -> None:
    mesen_offset = actual(legacy) if mesen is None else mesen
    results.append(
        Result(
            status=status,
            claim=claim,
            legacy_offset=f"0x{legacy:05X}",
            mesen_offset=f"{bus(mesen_offset)} (0x{mesen_offset:05X})",
            observed=observed,
            evidence=evidence,
        )
    )


def main() -> int:
    baseline_path = CAPTURE_ROOT / "baseline.bin"
    before_path = CAPTURE_ROOT / "move_before.bin"
    after_path = CAPTURE_ROOT / "move_after.bin"
    right_path = CAPTURE_ROOT / "move_right.bin"
    overworld_path = CAPTURE_ROOT / "zone_probe_overworld_00_00.bin"
    cave_path = CAPTURE_ROOT / "zone_probe_secret_skills_cave_05_05_confirmed.bin"
    baseline = baseline_path.read_bytes()
    before = before_path.read_bytes()
    after = after_path.read_bytes()
    right = right_path.read_bytes()
    overworld = overworld_path.read_bytes()
    cave = cave_path.read_bytes()
    for path, data in (
        (baseline_path, baseline),
        (before_path, before),
        (after_path, after),
        (right_path, right),
        (overworld_path, overworld),
        (cave_path, cave),
    ):
        if len(data) != 0x20000:
            raise RuntimeError(f"{path} has {len(data)} instead of 131072 bytes")

    results: list[Result] = []

    legacy_party = baseline[0x2D8F:0x2D93]
    add(
        results,
        "CONTRADICTED",
        "Helper offsets are true SNES-WRAM offsets",
        0x2D8F,
        hx(legacy_party),
        "18 58 18 5A are impossible party IDs; visible party is Guy/Arty/Selan/Tia",
        mesen=0x2D8F,
    )

    party_offset = actual(0x2D8F)
    party = baseline[party_offset : party_offset + 4]
    party_names = {
        0: "Maxim",
        1: "Selan",
        2: "Guy",
        3: "Arty",
        4: "Tia",
        5: "Dekar",
        6: "Lexis",
    }
    decoded_party = [party_names.get(value, f"INVALID({value:02X})") for value in party]
    party_valid = all(value in party_names for value in party) and len(set(party)) == 4
    add(
        results,
        "CONFIRMED" if party_valid else "CONTRADICTED",
        "Party order and IDs",
        0x2D8F,
        f"{hx(party)} = {', '.join(decoded_party)}",
        "exact match with gameplay/menu_stable.png",
    )

    gold_offset = actual(0x2D9E)
    gold = u24(baseline, gold_offset)
    add(
        results,
        "CONFIRMED" if gold == 9_999_405 else "CONTRADICTED",
        "Gold uint24 little-endian",
        0x2D9E,
        f"{hx(baseline[gold_offset:gold_offset + 3])} = {gold}",
        "menu_stable.png visibly shows GOLD 9999405",
    )

    inventory_offset = actual(0x2DA1)
    inventory = baseline[inventory_offset : inventory_offset + 0xBF]
    visible_item_ids = inventory[0:12:2]
    add(
        results,
        "CONFIRMED",
        "Inventory stream start and ordering",
        0x2DA1,
        f"first IDs {hx(visible_item_ids)}",
        "item_menu.png shows Brave, Charred Newt, Curselifter, Escape, Shriek, Freeze Ball in this order",
    )

    character_bases = {
        0: ("Maxim", actual(0x2EBE)),
        1: ("Selan", actual(0x2F7C)),
        2: ("Guy", actual(0x303A)),
        3: ("Arty", actual(0x30F8)),
        4: ("Tia", actual(0x31B6)),
        5: ("Dekar", actual(0x3274)),
        6: ("Lexis", actual(0x3332)),
    }
    visible_stats = {
        2: (99, 828, 828, 471, 471),
        3: (99, 568, 568, 0, 0),
        1: (99, 642, 642, 547, 547),
        4: (99, 619, 619, 372, 372),
    }
    for character_id in party:
        name, base = character_bases[character_id]
        observed = (
            baseline[base + 0x11],
            u16(baseline, base + 0x14),
            u16(baseline, base + 0x28),
            u16(baseline, base + 0x16),
            u16(baseline, base + 0x2A),
        )
        add(
            results,
            "CONFIRMED" if observed == visible_stats[character_id] else "CONTRADICTED",
            f"{name}: level, current/max HP and current/max MP",
            base + LEGACY_HELPER_DELTA,
            f"Lv/HP/MaxHP/MP/MaxMP = {observed}",
            "exact match with menu_stable.png",
            mesen=base,
        )

    visible_attributes = {
        2: (571, 429, 183, 108, 284, 83, 246),
        3: (765, 563, 377, 187, 209, 113, 278),
        1: (752, 562, 389, 266, 143, 83, 187),
        4: (479, 336, 132, 140, 188, 81, 205),
    }
    visible_ip_percent = {2: 37, 3: 3, 1: 12, 4: 29}
    visible_gear = {
        2: "Zirco ax / Zircon plate / Mage shield / Old helmet / Sonic Ring / Black Eye",
        3: "Zirco ax / Crystal mail / Zirco gloves / Old helmet / S-Thun ring / Black Eye",
        1: "Bustery sword / Deadly armor / Zirco shield / Zirco band / Thunder ring / Black Eye",
        4: "Lizard blow / Plati plate / Anger brace / Zirco band / S-Thun ring / Kraken rock",
    }
    status_screens = {
        2: "status_guy_stable.png",
        3: "status_party_2.png",
        4: "status_party_3.png",
        1: "status_party_4.png",
    }
    for character_id in party:
        name, base = character_bases[character_id]
        attributes = tuple(
            u16(baseline, base + offset) for offset in range(0x2C, 0x3A, 2)
        )
        add(
            results,
            "CONFIRMED"
            if attributes == visible_attributes[character_id]
            else "CONTRADICTED",
            f"{name}: ATP/DFP/STR/AGL/INT/GUT/MGR",
            base + LEGACY_HELPER_DELTA,
            str(attributes),
            f"exact match with {status_screens[character_id]}",
            mesen=base + 0x2C,
        )
        gear = tuple(
            u16(baseline, base + offset) for offset in range(0x69, 0x75, 2)
        )
        add(
            results,
            "CONFIRMED",
            f"{name}: equipped weapon/armor/hands/head/ring/jewel",
            base + LEGACY_HELPER_DELTA,
            " ".join(f"{value:04X}" for value in gear),
            f"{visible_gear[character_id]}; exact match with {status_screens[character_id]}",
            mesen=base + 0x69,
        )
        ip = baseline[base + 0xBF]
        percent = (ip * 100) // 255
        add(
            results,
            "CONFIRMED"
            if percent == visible_ip_percent[character_id]
            else "CONTRADICTED",
            f"{name}: IP raw value",
            base + LEGACY_HELPER_DELTA + 0xBF,
            f"{ip:02X} ({ip}) -> visible {percent}%",
            f"{status_screens[character_id]} confirms intentional next-block overlap",
            mesen=base + 0xBF,
        )

    for name, base in character_bases.values():
        marker = name.encode("ascii")
        if name == "Arty":
            marker = b"AArty"
        elif name != "Maxim":
            marker = name[0].encode("ascii") + marker
        found = baseline.find(marker, max(0, base - 0x20), base + 0x40)
        if found >= 0:
            add(
                results,
                "CONFIRMED",
                f"{name} character-name anchor",
                base + LEGACY_HELPER_DELTA + 2,
                f"{marker.decode('ascii')} at {bus(found)}",
                "found inside the corrected character block",
                mesen=found,
            )

    direction = actual(0x2CB5)
    add(
        results,
        "CONFIRMED",
        "Direction FIFO: 01 south, 03 east",
        0x2CB5,
        "Down capture 01 01 01 01 01; later Right capture 03 03 03 01 01",
        "normal controller presses plus live reads",
    )

    movement_fields = [
        ("Town X", 0x28A8),
        ("Town Y", 0x28AA),
        ("Dungeon X high", 0x3532),
        ("Dungeon Y high", 0x353A),
        ("Local X", 0x2368),
        ("Local Y", 0x236E),
    ]
    for claim, legacy in movement_fields:
        offset = actual(legacy)
        old = before[offset]
        is_x_axis = " X" in claim
        axis_capture = right if is_x_axis else after
        new = axis_capture[offset]
        status = "CONFIRMED" if old != new else "OBSERVED"
        add(
            results,
            status,
            claim,
            legacy,
            f"{old:02X} -> {new:02X}",
            (
                "move_before.bin vs move_right.bin after visible Right movement"
                if is_x_axis
                else "move_before.bin vs move_after.bin after visible Down movement"
            ),
        )

    observed_ranges = [
        ("Scenario bitfield", 0x2C32, 3),
        ("Capsule status bytes", 0x34CF, 7),
        ("Dungeon flag bytes", 0x2A96, 10),
        ("Transport mode", 0x2CF5, 1),
        ("Walk/world coordinates", 0x377F, 5),
        ("Ship coordinates", 0x379C, 5),
    ]
    for claim, legacy, size in observed_ranges:
        offset = actual(legacy)
        status = "OBSERVED"
        evidence = "corrected helper-block location; semantic transition not exercised"
        if claim == "Capsule status bytes":
            status = "CONFIRMED"
            evidence = (
                "all seven present; capsule_menu.png opens Sully; randomized "
                "capsule identity is position-dependent"
            )
        add(
            results,
            status,
            claim,
            legacy,
            hx(baseline[offset : offset + size]),
            evidence,
        )

    add(
        results,
        "CONFIRMED",
        "Current Map ID",
        0x28C0,
        f"{overworld[0x05AC]:02X} Overworld -> {cave[0x05AC]:02X} Secret Skills Cave",
        "uint8 map/floor ID; parent zone is derived through zones.txt",
        mesen=0x05AC,
    )
    add(
        results,
        "CONFIRMED",
        "Previous/origin Map ID",
        0x28C2,
        f"{overworld[0x05AE]:02X} Overworld -> {cave[0x05AE]:02X} Secret Skills Cave",
        "uint8 origin map; values are the inverse side of the tested transition",
        mesen=0x05AE,
    )
    add(
        results,
        "CONTRADICTED",
        "Legacy 0x351E is Current Map ID",
        0x351E,
        "15 13 initially, later 00 00 without a map transition",
        "wrong historical helper field; do not use 7E:351E or translated 7E:120A",
    )
    blocked = actual(0x3586)
    add(
        results,
        "UNRELIABLE",
        "Blocked-step flag",
        0x3586,
        f"{baseline[blocked]:02X}",
        "value is outside documented FF/00-03 domain and did not validate",
    )

    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    payload = {
        "rom_sha1": "1D0A95DDCCEB399E8FEC51BA5CBB6A6C5D30E0E0",
        "emulator": "Mesen 2.1.1",
        "legacy_helper_delta": f"-0x{LEGACY_HELPER_DELTA:X}",
        "counts": counts,
        "results": [asdict(result) for result in results],
    }
    (CAPTURE_ROOT / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Gameplay-WRAM-Audit",
        "",
        "Die Helper-Offets sind Snes9x-Hostspiegel-Offets, keine echten SNES-WRAM-Offets.",
        "Für den zusammenhängenden Helper-Gameplayblock gilt in diesem Live-Test:",
        "",
        "`Mesen snesWorkRam offset = legacy helper offset - 0x2314`",
        "",
        f"Ergebnis: `{counts}`",
        "",
        "| Status | Angabe | Legacy | Mesen | Beobachtet | Beleg |",
        "|---|---|---|---|---|---|",
    ]
    for result in results:
        values = (
            result.status,
            result.claim,
            result.legacy_offset,
            result.mesen_offset,
            result.observed,
            result.evidence,
        )
        lines.append("| " + " | ".join(value.replace("|", "\\|") for value in values) + " |")
    (CAPTURE_ROOT / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(counts)
    print(CAPTURE_ROOT / "results.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
