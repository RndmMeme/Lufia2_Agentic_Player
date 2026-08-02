"""
WRAM Boot Analyzer
==================
Vergleicht zwei WRAM-Dumps (base vs boot) und identifiziert Addressen
die sich beim Booten des Spiels aendern (NATSUME-Logo).

Ergebnisse: Excel (.xlsx), CSV, und eine Liste von Boot-Hook-Kandidaten.

Nutzung:
    python wram_discovery/boot_analyzer.py

Setzt voraus das die beiden .dmp Dateien im selben Ordner liegen.
"""

import os
import csv
import re
import sys
from pathlib import Path
from typing import List, Tuple, Dict

WRAM_DIR = Path(__file__).parent  # wram_discovery/

# ========================================================================
# BEKANNTE WRAM-BEREICHE (SNES 7E:0000 - 7E:FFFF, 7F:0000 - 7F:FFFF)
# ========================================================================
WRAM_REGIONS = {
    (0x00000, 0x007FF): "Stack + Direct Page (7E:0000-07FF)",
    (0x00800, 0x00FFF): "WRAM Mirror / System Work",
    (0x01000, 0x01FFF): "DMA/HDMA Buffers",
    (0x02000, 0x02FFF): "Sprite / OAM Shadow",
    (0x03000, 0x03FFF): "Tilemap / BG3",
    (0x04000, 0x04FFF): "Palette Shadow / CGRAM",
    (0x05000, 0x05FFF): "Sound / APU Communication",
    (0x06000, 0x06FFF): "Event Script Variables",
    (0x07000, 0x07FFF): "Event Flags (0x077E-079D) + Script Work",
    (0x08000, 0x0FFFF): "General Game State",
    (0x10000, 0x10FFF): "NPC / Object Data (Slot 0-15)",
    (0x11000, 0x11FFF): "NPC / Object Data (Slot 16-31)",
    (0x12000, 0x12FFF): "Map Tile Data (Layer 1)",
    (0x13000, 0x13FFF): "Map Tile Data (Layer 2)",
    (0x14000, 0x14FFF): "Collision Map Data",
    (0x15000, 0x15FFF): "Room Object States",
    (0x16000, 0x16FFF): "Dungeon Puzzle States",
    (0x17000, 0x17FFF): "World Map Data / Warp Table",
    (0x18000, 0x18FFF): "Menu / Subscreen Buffers",
    (0x19000, 0x19FFF): "Text Buffer / Dialogue",
    (0x1A000, 0x1AFFF): "Inventory / Item Data (0x2DA1+)",
    (0x1B000, 0x1BFFF): "Party / Character Stats (0x2EBE+)",
    (0x1C000, 0x1CFFF): "Enemy Data (0x3940+)",
    (0x1D000, 0x1DFFF): "Battle State / Animation",
    (0x1E000, 0x1EFFF): "Unused / Expansion",
    (0x1F000, 0x1FFFF): "Save Slot Data Mirror",
}

# Bekannte Boot-Indikatoren (Werte die auf "Spiel bootet" hindeuten)
BOOT_INDICATORS = {
    0x2D9E: "Gold (0 = kein Save geladen)",
    0x28C0: "CurrentMap (bootet auf 0x0000 oder 0xFFFF)",
    0x2D8F: "PartySlot1 (0xFF = leer/kein Save)",
    0x2CF5: "TransportFlag (0x00 = walk, bootet auf bestimmten Wert)",
}

# Natsume-logo-spezifisch: Addressen die nur waehrend Logo anders sind
NATSUME_SIGNATURES = {
    "Intro/Logo aktiv": [],  # Hier landen Kandidaten die stabil auf 1/0 umschalten
}


def snes_addr(offset: int) -> str:
    """Wandelt Offset 0-131071 in SNES WRAM-Addresse um."""
    if offset < 0x10000:
        return f"7E:{offset:04X}"
    else:
        return f"7F:{offset - 0x10000:04X}"


def get_region(offset: int) -> str:
    """Gibt die WRAM-Region fuer einen Offset zurueck."""
    for (start, end), label in WRAM_REGIONS.items():
        if start <= offset <= end:
            return label
    # Fallback: nach Bank aufteilen
    if offset < 0x10000:
        return f"7E:{offset:04X} (unbekannt)"
    else:
        return f"7F:{offset - 0x10000:04X} (unbekannt)"


def diff_dumps(before: bytes, after: bytes) -> List[dict]:
    """Vergleicht zwei WRAM-Dumps Byte-fuer-Byte."""
    if len(before) != len(after):
        raise ValueError(f"Groessen mismatch: {len(before)} vs {len(after)}")

    changes = []
    for offset in range(len(before)):
        o, n = before[offset], after[offset]
        if o != n:
            changes.append({
                "offset_dec": offset,
                "offset_hex": f"0x{offset:05X}",
                "snes_addr": snes_addr(offset),
                "region": get_region(offset),
                "old_val": o,
                "new_val": n,
                "old_hex": f"0x{o:02X}",
                "new_hex": f"0x{n:02X}",
                "delta": n - o,
                "changed_bits": o ^ n,
                "bits_set_old": bin(o).count("1"),
                "bits_set_new": bin(n).count("1"),
                "stable_value": n,  # Wert nach Boot
            })
    return changes


def categorize_changes(changes: List[dict]) -> dict:
    """Kategorisiert Aenderungen nach WRAM-Region."""
    cats = {}
    for c in changes:
        region = c["region"]
        if region not in cats:
            cats[region] = []
        cats[region].append(c)
    return cats


def find_boot_candidates(changes: List[dict]) -> List[dict]:
    """
    Findet Boot-Hook-Kandidaten:
    - Addressen die von 0x00 auf einen stabilen Wert springen
    - Addressen die nur 1 Bit togglen (Flag-Charakter)
    - Addressen im Bereich 0x0700-0x0800 (Event Flags)
    - Addressen die NUR beim Boot, nie im Spiel veraendert werden
    """
    candidates = []
    for c in changes:
        score = 0
        reasons = []

        # Kriterium 1: Wert wurde von 0x00 auf etwas gesetzt (Initialisierung)
        if c["old_val"] == 0x00 and c["new_val"] != 0x00:
            score += 3
            reasons.append("Initialisierung 0x00 -> Wert")

        # Kriterium 2: Nur 1 Bit geaendert (Flag)
        bit_count = bin(c["changed_bits"]).count("1")
        if bit_count == 1:
            score += 2
            reasons.append(f"1-Bit-Flag (Bit {c['changed_bits'].bit_length() - 1})")
        elif bit_count <= 3:
            score += 1
            reasons.append(f"Kompakt ({bit_count} Bits)")

        # Kriterium 3: Im Event-Flag-Bereich (0x077E-0x079D)
        if 0x077E <= c["offset_dec"] <= 0x079D:
            score += 5
            reasons.append("Event-Flag-Bereich!")

        # Kriterium 4: Im Dungeon-Flag-Bereich (0x2A96-0x2A9F)
        if 0x2A96 <= c["offset_dec"] <= 0x2A9F:
            score += 4
            reasons.append("Dungeon-Flag-Bereich!")

        # Kriterium 5: Gold/Map/Party (Boot-Indikatoren)
        if c["offset_dec"] in BOOT_INDICATORS:
            score += 5
            reasons.append(f"Bekannter Boot-Indikator: {BOOT_INDICATORS[c['offset_dec']]}")

        # Kriterium 6: Wert ist 0x01 oder 0x00 (bool)
        if c["new_val"] in (0x00, 0x01) and c["old_val"] in (0x00, 0x01) and c["old_val"] != c["new_val"]:
            score += 2
            reasons.append("Boolean (0/1)")

        # Kriterium 7: Wert wiederholt sich (stabiler Indikator)
        stable_patterns = [0x01, 0xFF, 0x00]
        if c["stable_value"] in stable_patterns:
            score += 1
            reasons.append(f"Stabiler Wert: 0x{c['stable_value']:02X}")

        if score >= 3:  # Nur vielversprechende Kandidaten
            candidates.append({
                **c,
                "boot_score": score,
                "reasons": "; ".join(reasons),
            })

    candidates.sort(key=lambda x: x["boot_score"], reverse=True)
    return candidates


def export_csv(changes: List[dict], path: Path):
    """Exportiert alle Aenderungen als CSV (Semikolon-getrennt)."""
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([
            "Offset", "SNES-Adresse", "Region",
            "Vorher", "Nachher", "Vorher-Hex", "Nachher-Hex",
            "Delta", "Bits geaendert", "BootScore"
        ])
        for c in changes:
            w.writerow([
                c["offset_hex"], c["snes_addr"], c["region"],
                c["old_val"], c["new_val"], c["old_hex"], c["new_hex"],
                c["delta"], c["changed_bits"], c.get("boot_score", ""),
            ])


def export_excel(changes: List[dict], candidates: List[dict], categories: dict, path: Path):
    """Exportiert als Excel (.xlsx) mit mehreren Sheets."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        print("  openpyxl nicht installiert. Fallback auf CSV.")
        export_csv(changes, path.with_suffix(".csv"))
        return

    wb = openpyxl.Workbook()

    # === Sheet 1: Boot-Kandidaten ===
    ws1 = wb.active
    ws1.title = "Boot-Kandidaten"
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    candidate_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    headers = ["Score", "Offset", "SNES-Addresse", "Region", "Vorher", "Nachher",
               "Bits", "Begruendung"]
    for col, h in enumerate(headers, 1):
        cell = ws1.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal="center")

    for row, c in enumerate(candidates, 2):
        values = [c["boot_score"], c["offset_hex"], c["snes_addr"],
                  c["region"], c["old_hex"], c["new_hex"],
                  bin(c["changed_bits"]).count("1"), c["reasons"]]
        for col, val in enumerate(values, 1):
            cell = ws1.cell(row=row, column=col, value=val)
            cell.border = thin_border
            if c["boot_score"] >= 8:
                cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
            elif c["boot_score"] >= 5:
                cell.fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")

    ws1.column_dimensions['A'].width = 8
    ws1.column_dimensions['B'].width = 12
    ws1.column_dimensions['C'].width = 14
    ws1.column_dimensions['D'].width = 40
    ws1.column_dimensions['E'].width = 10
    ws1.column_dimensions['F'].width = 10
    ws1.column_dimensions['G'].width = 8
    ws1.column_dimensions['H'].width = 60

    # === Sheet 2: Alle Aenderungen ===
    ws2 = wb.create_sheet("Alle Aenderungen")
    headers2 = ["Offset", "SNES-Addr", "Region", "Vorher", "Nachher", "Delta", "Bits"]
    for col, h in enumerate(headers2, 1):
        cell = ws2.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border

    for row, c in enumerate(changes, 2):
        values = [c["offset_hex"], c["snes_addr"], c["region"],
                  c["old_hex"], c["new_hex"], c["delta"],
                  bin(c["changed_bits"]).count("1")]
        for col, val in enumerate(values, 1):
            cell = ws2.cell(row=row, column=col, value=val)
            cell.border = thin_border

    ws2.column_dimensions['A'].width = 12
    ws2.column_dimensions['B'].width = 14
    ws2.column_dimensions['C'].width = 45
    ws2.column_dimensions['D'].width = 10
    ws2.column_dimensions['E'].width = 10
    ws2.column_dimensions['F'].width = 8
    ws2.column_dimensions['G'].width = 8

    # === Sheet 3: Zusammenfassung nach Region ===
    ws3 = wb.create_sheet("Nach Region")
    headers3 = ["Region", "Anzahl Aenderungen", "Beispiele"]
    for col, h in enumerate(headers3, 1):
        cell = ws3.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border

    row = 2
    for region, region_changes in sorted(categories.items(),
                                         key=lambda x: len(x[1]), reverse=True):
        examples = ", ".join(c["snes_addr"] for c in region_changes[:5])
        if len(region_changes) > 5:
            examples += f" ... (+{len(region_changes)-5})"
        for col, val in enumerate([region, len(region_changes), examples], 1):
            cell = ws3.cell(row=row, column=col, value=val)
            cell.border = thin_border
        row += 1

    ws3.column_dimensions['A'].width = 50
    ws3.column_dimensions['B'].width = 20
    ws3.column_dimensions['C'].width = 80

    wb.save(path)
    print(f"  Excel exportiert: {path}")


def main():
    print()
    print("=" * 60)
    print("  WRAM BOOT ANALYZER")
    print("  Findet Boot-Hook-Kandidaten im WRAM-Diff")
    print("=" * 60)
    print()

    # Dumps automatisch finden
    dumps = sorted(WRAM_DIR.glob("*.dmp"))
    base_dump = None
    boot_dump = None

    for d in dumps:
        name = d.stem.lower()
        if "base" in name:
            base_dump = d
        elif "boot" in name or "natsume" in name:
            boot_dump = d

    if not base_dump or not boot_dump:
        print("  Dumps nicht gefunden! Erwarte:")
        print(f"    - base.dmp (WRAM vor Spielstart)")
        print(f"    - boot_natsume.dmp (WRAM mit NATSUME Logo)")
        print(f"  In: {WRAM_DIR}")
        print()
        print("  Gefundene .dmp Dateien:")
        for d in dumps:
            print(f"    {d.name}")
        sys.exit(1)

    print(f"  Basis-Dump:  {base_dump.name}")
    print(f"  Boot-Dump:   {boot_dump.name}")
    print()

    # Laden
    before = base_dump.read_bytes()
    after = boot_dump.read_bytes()

    print(f"  Groesse: {len(before):,} Bytes (128KB)")
    print()

    # Diff
    changes = diff_dumps(before, after)
    categories = categorize_changes(changes)
    candidates = find_boot_candidates(changes)

    print(f"  Geaenderte Bytes: {len(changes):,}")
    print(f"  Boot-Kandidaten:  {len(candidates)}")
    print()

    # Regionen-Zusammenfassung
    print("  Aenderungen nach Region:")
    for region, region_changes in sorted(categories.items(),
                                         key=lambda x: len(x[1]), reverse=True):
        print(f"    {region}: {len(region_changes)}")
    print()

    # Top-Kandidaten ausgeben
    print("  TOP 20 Boot-Hook-Kandidaten:")
    print(f"  {'Score':>5} {'Offset':<12} {'SNES-Addr':<12} "
          f"{'Aenderung':<12} {'Begruendung'}")
    print(f"  {'-'*5} {'-'*12} {'-'*12} {'-'*12} {'-'*50}")
    for c in candidates[:20]:
        changed_str = f"{c['old_hex']} -> {c['new_hex']}"
        print(f"  {c['boot_score']:>5} {c['offset_hex']:<12} "
              f"{c['snes_addr']:<12} {changed_str:<12} {c['reasons'][:50]}")

    # Export
    out_csv = WRAM_DIR / "boot_diff.csv"
    out_xlsx = WRAM_DIR / "boot_diff.xlsx"
    out_candidates = WRAM_DIR / "boot_candidates.txt"

    export_csv(changes, out_csv)
    print(f"\n  CSV: {out_csv}")

    export_excel(changes, candidates, categories, out_xlsx)

    # Boot-Kandidaten als Text
    with out_candidates.open("w", encoding="utf-8") as f:
        f.write("WRAM BOOT HOOK KANDIDATEN\n")
        f.write(f"Basis: {base_dump.name}\n")
        f.write(f"Boot:  {boot_dump.name}\n")
        f.write(f"Gefundene Aenderungen: {len(changes)}\n")
        f.write(f"Kandidaten: {len(candidates)}\n\n")
        f.write(f"{'Score':>5} | {'Offset':<10} | {'SNES':<12} | "
                f"{'Alt':<8} | {'Neu':<8} | {'Bits':<5} | Begruendung\n")
        f.write("-" * 100 + "\n")
        for c in candidates:
            bits = bin(c["changed_bits"]).count("1")
            f.write(f"{c['boot_score']:>5} | {c['offset_hex']:<10} | "
                    f"{c['snes_addr']:<12} | {c['old_hex']:<8} | "
                    f"{c['new_hex']:<8} | {bits:<5} | {c['reasons']}\n")

    print(f"  Kandidaten: {out_candidates}")
    print(f"  Excel:      {out_xlsx}")
    print()
    print("  Fertig! Boot-Hook => boot_candidates.txt")
    print()


if __name__ == "__main__":
    main()