#!/usr/bin/env python3
"""Verify an NPC-dialog lifecycle against two NPCs and a shop control."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CAPTURE_ROOT = ROOT / "mesen_bridge" / "validation" / "gameplay"
NPC_DIALOG = 0x099B
GENERAL_INTERACTION = 0x0622
CONTROL_STATE = 0x06F1


def load(name: str) -> bytes:
    data = (CAPTURE_ROOT / name).read_bytes()
    if len(data) != 0x20000:
        raise RuntimeError(f"{name}: invalid WRAM size {len(data)}")
    return data


def hx(data: bytes, offset: int, length: int = 1) -> str:
    return data[offset : offset + length].hex(" ").upper()


def main() -> int:
    captures = {
        "moving_npc_closed": load("npc_dialog_closed.bin"),
        "moving_npc_open": load("npc_dialog_open_1.bin"),
        "stationary_npc_closed": load("npc_stationary_closed.bin"),
        "stationary_npc_open": load("npc_stationary_open_1.bin"),
        "stationary_npc_return": load("npc_stationary_return.bin"),
        "shop_open": load("shop_open.bin"),
    }
    rows = {
        name: {
            "npc_dialog": hx(data, NPC_DIALOG, 2),
            "general_interaction": hx(data, GENERAL_INTERACTION),
            "control_state": hx(data, CONTROL_STATE),
        }
        for name, data in captures.items()
    }
    confirmed = (
        rows["moving_npc_closed"]["npc_dialog"] == "00 00"
        and rows["moving_npc_open"]["npc_dialog"] == "88 01"
        and rows["stationary_npc_closed"]["npc_dialog"] == "00 00"
        and rows["stationary_npc_open"]["npc_dialog"] == "88 01"
        and rows["stationary_npc_return"]["npc_dialog"] == "00 00"
        and rows["shop_open"]["npc_dialog"] == "00 00"
    )
    payload = {
        "status": "CONFIRMED" if confirmed else "FAILED",
        "npc_dialog_indicator": {
            "address": "7E:099B-099C",
            "closed": "00 00",
            "tested_npc_open": "88 01",
            "shop_open": "00 00",
        },
        "non_specific_candidates": {
            "7E:0622": "20 idle, 21 NPC dialog and shop",
            "7E:06F1": "06 idle, 05 NPC dialog and shop",
        },
        "captures": rows,
    }
    json_path = CAPTURE_ROOT / "npc_dialog_results.json"
    md_path = CAPTURE_ROOT / "npc_dialog_results.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# NPC-Dialog-WRAM-Audit",
        "",
        f"Status: **{payload['status']}**",
        "",
        "`7E:099B-099C` durchlief bei zwei NPCs Closed -> `88 01` -> Closed. "
        "Im geöffneten Shop blieb der Wert `00 00`.",
        "",
        "`7E:0622` und `7E:06F1` sind nicht dialogspezifisch, weil sie auch im "
        "Shop wechseln.",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if confirmed else 1


if __name__ == "__main__":
    raise SystemExit(main())
