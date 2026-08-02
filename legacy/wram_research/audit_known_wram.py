#!/usr/bin/env python3
"""Reproducible live audit for already documented Lufia II WRAM values.

The audit deliberately distinguishes exact live evidence from source-only
claims which cannot be exercised in the current emulator state.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from mesen_bridge import MesenFileBridge, SAVE_CURSOR_VALUES, WRAM_SIZE


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "mesen_bridge" / "validation" / "known_values_audit"
UI_HOST_DELTA = 0x2314
NAME_CURSOR_OFFSET = 0x0100


@dataclass
class Result:
    claim: str
    status: str
    address: str
    expected: str
    observed: str
    evidence: str


def address(offset: int) -> str:
    if offset < 0x10000:
        return f"7E:{offset:04X}"
    return f"7F:{offset - 0x10000:04X}"


def hex_bytes(value: bytes) -> str:
    return value.hex(" ").upper()


def host_to_offset(host_address: int) -> int:
    """Known UI-buffer relation; not a general Snes9x-to-WRAM conversion."""
    return (host_address & 0xFFFF) - UI_HOST_DELTA


def exact(
    results: list[Result],
    dump: bytes,
    claim: str,
    offset: int,
    expected: bytes,
    evidence: str,
) -> None:
    observed = dump[offset : offset + len(expected)]
    results.append(
        Result(
            claim=claim,
            status="CONFIRMED" if observed == expected else "CONTRADICTED",
            address=f"{address(offset)}-{address(offset + len(expected) - 1)}",
            expected=hex_bytes(expected),
            observed=hex_bytes(observed),
            evidence=evidence,
        )
    )


def unavailable(
    results: list[Result],
    claim: str,
    address_text: str,
    reason: str,
) -> None:
    results.append(
        Result(
            claim=claim,
            status="NOT_ACTIVE",
            address=address_text,
            expected="",
            observed="",
            evidence=reason,
        )
    )


def pulse_to(
    bridge: MesenFileBridge,
    results: list[Result],
    button: str,
    count: int,
    expected: bytes,
    label: str,
) -> None:
    for _ in range(count):
        bridge.pulse(button)
    observed = bridge.read(NAME_CURSOR_OFFSET, 2)
    results.append(
        Result(
            claim=f"Namenscursor {label}",
            status="CONFIRMED" if observed == expected else "CONTRADICTED",
            address="7E:0100-7E:0101",
            expected=hex_bytes(expected),
            observed=hex_bytes(observed),
            evidence=f"nach {count} kontrollierten {button.upper()}-Einzelschritten",
        )
    )


def audit_name_grid(
    bridge: MesenFileBridge,
    results: list[Result],
    output: Path,
) -> None:
    initial = bridge.read(NAME_CURSOR_OFFSET, 2)
    results.append(
        Result(
            claim="Namenscursor (0,0)",
            status="CONFIRMED" if initial == bytes.fromhex("2D 43") else "CONTRADICTED",
            address="7E:0100-7E:0101",
            expected="2D 43",
            observed=hex_bytes(initial),
            evidence="Live-Startposition im Namensbildschirm",
        )
    )
    if initial != bytes.fromhex("2D 43"):
        return

    checkpoints = [
        ("right", 9, "C5 43", "(9,0)"),
        ("down", 1, "C5 53", "(9,1)"),
        ("left", 9, "2D 53", "(0,1)"),
        ("down", 1, "2D 63", "(0,2)"),
        ("right", 9, "C5 63", "(9,2)"),
        ("down", 1, "C5 73", "(9,3)"),
        ("left", 9, "2D 73", "(0,3)"),
        ("down", 1, "2D 83", "(0,4)"),
        ("right", 9, "C5 83", "(9,4)"),
        ("down", 1, "C5 93", "(9,5)"),
        ("left", 9, "2D 93", "(0,5)"),
        ("down", 1, "2D A3", "(0,6)"),
        ("right", 7, "A5 A3", "(7,6)"),
    ]
    for button, count, expected, label in checkpoints:
        pulse_to(bridge, results, button, count, bytes.fromhex(expected), label)

    _, screenshot = bridge.probe(NAME_CURSOR_OFFSET, 2)
    (output / "name_grid_last_checkpoint.png").write_bytes(screenshot)


def audit_static_name_screen(dump: bytes, results: list[Result]) -> None:
    claims = [
        ("NAME-Überschrift", 0xA35460, "4E 20 41 20 4D 20 45 20"),
        ("Namensfeld initial", 0xA35476, "30 20 5F 20 5F 20 5F 20 5F 20"),
        (
            "Ziffern 0-9",
            0xA35560,
            "30 20 20 20 31 20 20 20 32 20 20 20 33 20 20 20 "
            "34 20 20 20 20 20 35 20 20 20 36 20 20 20 37 20 "
            "20 20 38 20 20 20 39 20",
        ),
        (
            "Großbuchstaben A-E",
            0xA355E0,
            "41 20 20 20 42 20 20 20 43 20 20 20 44 20 20 20 45",
        ),
        (
            "Kleinbuchstaben a-e",
            0xA355F6,
            "61 20 20 20 62 20 20 20 63 20 20 20 64 20 20 20 65",
        ),
        (
            "Großbuchstaben F-J",
            0xA35660,
            "46 20 20 20 47 20 20 20 48 20 20 20 49 20 20 20 4A",
        ),
        (
            "Kleinbuchstaben f-j",
            0xA35676,
            "66 20 20 20 67 20 20 20 68 20 20 20 69 20 20 20 6A",
        ),
        (
            "Großbuchstaben K-O",
            0xA356E0,
            "4B 20 20 20 4C 20 20 20 4D 20 20 20 4E 20 20 20 4F",
        ),
        (
            "Kleinbuchstaben k-o",
            0xA356F6,
            "6B 20 20 20 6C 20 20 20 6D 20 20 20 6E 20 20 20 6F",
        ),
        (
            "Großbuchstaben P-T",
            0xA35760,
            "50 20 20 20 51 20 20 20 52 20 20 20 53 20 20 20 54",
        ),
        (
            "Kleinbuchstaben p-t",
            0xA35776,
            "70 20 20 20 71 20 20 20 72 20 20 20 73 20 20 20 74",
        ),
        (
            "Großbuchstaben U-Y",
            0xA357E0,
            "55 20 20 20 56 20 20 20 57 20 20 20 58 20 20 20 59",
        ),
        (
            "Kleinbuchstaben u-y",
            0xA357F6,
            "75 20 20 20 76 20 20 20 77 20 20 20 78 20 20 20 79",
        ),
        ("Großbuchstaben Z ! ?", 0xA35860, "5A 20 20 20 21 20 20 20 3F"),
        ("Kleinbuchstaben z ! ?", 0xA35876, "7A 20 20 20 21 20 20 20 3F"),
    ]
    for label, host, expected in claims:
        offset = host_to_offset(host)
        exact(
            results,
            dump,
            label,
            offset,
            bytes.fromhex(expected),
            f"Legacy-UI-Adresse 0x{host:X}, lokal bestätigter UI-Versatz -0x{UI_HOST_DELTA:X}",
        )


def audit_selection_screen(dump: bytes, results: list[Result]) -> None:
    exact(
        results,
        dump,
        "START-Text",
        0x30C8,
        bytes.fromhex("53 20 54 20 41 20 52 20 54 20"),
        "atomarer Live-Dump",
    )
    exact(
        results,
        dump,
        "RETRY-Text",
        0x30D8,
        bytes.fromhex("52 20 45 20 54 20 52 20 59 20"),
        "atomarer Live-Dump",
    )
    exact(
        results,
        dump,
        "GIFT-Text",
        0x30E8,
        bytes.fromhex("47 20 49 20 46 20 54 20"),
        "atomarer Live-Dump",
    )

    value = dump[0x0108:0x010A]
    meaning = SAVE_CURSOR_VALUES.get(value, "unbekannt")
    results.append(
        Result(
            claim="Auswahlcursor",
            status="CONFIRMED" if value in SAVE_CURSOR_VALUES else "CONTRADICTED",
            address="7E:0108-7E:0109",
            expected="eines der sieben bestätigten Bytepaare",
            observed=f"{hex_bytes(value)} ({meaning})",
            evidence="atomarer Live-Dump",
        )
    )

    # The currently loaded screen has Save 1 occupied and slots 2-4 empty.
    exact(
        results,
        dump,
        "Save 1 NAME",
        0x31C8,
        bytes.fromhex("4E 20 41 20 4D 20 45"),
        "sichtbarer belegter Save 1",
    )
    exact(
        results,
        dump,
        "Save 1 NAME-Trennbytes",
        0x31CF,
        bytes.fromhex("20 20 20"),
        "sichtbarer belegter Save 1",
    )
    exact(
        results,
        dump,
        "Save 1 TIME",
        0x3248,
        bytes.fromhex("54 20 49 20 4D 20 45"),
        "sichtbarer belegter Save 1",
    )
    exact(
        results,
        dump,
        "Save 1 TIME-Trennbytes",
        0x324F,
        bytes.fromhex("20 20 20"),
        "sichtbarer belegter Save 1",
    )
    exact(
        results,
        dump,
        "Save 1 Hero 1 Level 5",
        0x3386,
        bytes.fromhex("20 20 35"),
        "sichtbarer Levelwert im belegten Save 1",
    )
    for slot, offset in [(2, 0x31E6), (3, 0x3488), (4, 0x34A6)]:
        exact(
            results,
            dump,
            f"Save {slot} FREE",
            offset,
            bytes.fromhex("46 20 52 20 45 20 45 20"),
            f"sichtbarer leerer Save {slot}",
        )

    for slot in (2, 3, 4):
        unavailable(
            results,
            f"Save {slot}: Name, Zeit, Party und Level",
            "dokumentierte UI-Puffer",
            f"Slot {slot} ist leer; der Bildschirm rendert dort FREE statt der Felder",
        )


def write_report(
    output: Path,
    state: dict,
    screen: str,
    results: list[Result],
) -> None:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "emulator": "Mesen",
        "rom": state,
        "screen": screen,
        "counts": counts,
        "results": [asdict(result) for result in results],
    }
    (output / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Live-Audit der vorhandenen WRAM-Angaben",
        "",
        f"- ROM: `{state['rom_name']}`",
        f"- SHA-1: `{state['rom_sha1']}`",
        f"- WRAM: `{state['wram_size']}` Bytes",
        f"- Erkannter Bildschirm: `{screen}`",
        f"- Ergebnis: `{counts}`",
        "",
        "| Status | Angabe | Adresse | Erwartet | Beobachtet | Beleg |",
        "|---|---|---|---|---|---|",
    ]
    for result in results:
        cells = [
            result.status,
            result.claim,
            result.address,
            result.expected,
            result.observed,
            result.evidence,
        ]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    (output / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prüft dokumentierte Lufia-II-WRAM-Angaben live gegen Mesen."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--drive-name-grid",
        action="store_true",
        help="Testet im Namensbildschirm alle dokumentierten Cursor-Eckpunkte.",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    bridge = MesenFileBridge()
    state = bridge.ping()
    if state["wram_size"] != WRAM_SIZE:
        raise RuntimeError(f"Unerwartete WRAM-Größe: {state['wram_size']}")

    dump, screenshot = bridge.probe(0, WRAM_SIZE)
    (output / "live_wram.bin").write_bytes(dump)
    (output / "live_screen.png").write_bytes(screenshot)

    results: list[Result] = []
    if dump[0x314C:0x3154] == bytes.fromhex("4E 20 41 20 4D 20 45 20"):
        screen = "name"
        audit_static_name_screen(dump, results)
        if args.drive_name_grid:
            audit_name_grid(bridge, results, output)
    elif dump[0x30C8:0x30D2] == bytes.fromhex("53 20 54 20 41 20 52 20 54 20"):
        screen = "selection"
        audit_selection_screen(dump, results)
    else:
        screen = "other"
        unavailable(
            results,
            "Auswahl- und Namensbildschirm-Angaben",
            "",
            "Keiner der beiden bekannten Bildschirme ist aktiv",
        )

    write_report(output, state, screen, results)
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    print(f"Screen: {screen}")
    print(f"Results: {counts}")
    print(output / "results.md")
    return 2 if counts.get("CONTRADICTED", 0) else 0


if __name__ == "__main__":
    sys.exit(main())
