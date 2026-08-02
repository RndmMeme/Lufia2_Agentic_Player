#!/usr/bin/env python3
"""Verify the Mesen shop cursor, selected name and selected price captures."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CAPTURE_ROOT = ROOT / "mesen_bridge" / "validation" / "gameplay"
CURSOR = 0x1574
NAME = 0x0B77
NAME_LENGTH = 18
PRICE = 0x0B89
LEGACY_PRICE = 0x2CCE


def read_name(data: bytes) -> str:
    return data[NAME : NAME + NAME_LENGTH].split(b"\0", 1)[0].decode("ascii")


def main() -> int:
    expected = [
        ("shop_item_active_1.bin", "Hi-Potion", 95, 0x0000),
        ("shop_item_active_2.bin", "Confuse ball", 79, 0x000C),
        ("shop_item_active_3.bin", "Escape", 95, 0x0018),
    ]
    rows = []
    legacy_values = set()
    ok = True
    for filename, expected_name, expected_price, expected_cursor in expected:
        data = (CAPTURE_ROOT / filename).read_bytes()
        if len(data) != 0x20000:
            raise RuntimeError(f"{filename}: invalid WRAM size {len(data)}")
        name = read_name(data)
        price = int.from_bytes(data[PRICE : PRICE + 2], "little")
        cursor = int.from_bytes(data[CURSOR : CURSOR + 2], "little")
        legacy_price = data[LEGACY_PRICE : LEGACY_PRICE + 2].hex(" ").upper()
        passed = (name, price, cursor) == (
            expected_name,
            expected_price,
            expected_cursor,
        )
        ok &= passed
        legacy_values.add(legacy_price)
        rows.append(
            {
                "capture": filename,
                "name": name,
                "price": price,
                "cursor": cursor,
                "legacy_price_bytes": legacy_price,
                "passed": passed,
            }
        )

    payload = {
        "status": "CONFIRMED" if ok and len(legacy_values) == 1 else "FAILED",
        "addresses": {
            "selected_name": "7E:0B77 (ASCII, zero terminated)",
            "selected_price": "7E:0B89-0B8A (uint16 little-endian)",
            "shop_cursor": "7E:1574-1575 (uint16 little-endian, row stride 0x0C)",
            "legacy_price_0x2CCE": "CONTRADICTED",
        },
        "rows": rows,
    }
    json_path = CAPTURE_ROOT / "shop_results.json"
    md_path = CAPTURE_ROOT / "shop_results.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# Shop-WRAM-Audit",
        "",
        f"Status: **{payload['status']}**",
        "",
        "| Capture | Name @ 7E:0B77 | Preis @ 7E:0B89 | Cursor @ 7E:1574 | Ergebnis |",
        "|---|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['capture']} | {row['name']} | {row['price']} | "
            f"0x{row['cursor']:04X} | {'PASS' if row['passed'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "`0x2CCE` blieb in allen drei Zuständen unverändert und ist als "
            "ausgewählter Shoppreis für echtes Mesen-WRAM widerlegt.",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "CONFIRMED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
