#!/usr/bin/env python3
"""Record compact, transition-only battle WRAM observations from live Mesen.

The bridge can return a coherent 128-KiB dump every few emulated frames.  This
tool intentionally keeps only semantic changes, so menu transitions and combat
execution remain readable instead of becoming a wall of identical snapshots.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.battle.state import ACTIVE_ACTION_BASE, COMMAND_BASE, COMMAND_STRIDE, INITIATIVE_BASE
from agent.game_state import CHARACTER_BASE, CHARACTER_STRIDE, ENEMY_BASE, ENEMY_STRIDE, u16
from wram_discovery.mesen_bridge import MesenFileBridge


def _hex(value: int) -> str:
    return f"{value:02X}"


def decode(data: bytes) -> dict:
    formation = list(data[0x0A7B:0x0A7F])
    party_hp = []
    for identity in formation:
        if identity >= 7:
            party_hp.append(None)
            continue
        base = CHARACTER_BASE + identity * CHARACTER_STRIDE
        party_hp.append({
            "identity": identity,
            "hp": u16(data, base + 0x14),
            "mp": u16(data, base + 0x16),
            "status": _hex(data[base + 0x12]),
        })

    enemies = []
    for slot in range(6):
        base = ENEMY_BASE + slot * ENEMY_STRIDE
        hp = u16(data, base + 0x14)
        identity = data[base + 0x53]
        if hp or identity:
            enemies.append({
                "slot": slot,
                "identity": _hex(identity),
                "hp": hp,
                "mp": u16(data, base + 0x16),
                "status": _hex(data[base + 0x12]),
            })

    commands = []
    for slot in range(4):
        base = COMMAND_BASE + slot * COMMAND_STRIDE
        commands.append({
            "slot": slot,
            "target": _hex(data[base]),
            "command": _hex(data[base + 4]),
            "ability": f"{data[base + 7]:02X}{data[base + 6]:02X}",
            "actor": _hex(data[base + 10]),
        })

    initiative = []
    for slot in range(11):
        base = INITIATIVE_BASE + slot * 3
        actor = data[base]
        value = u16(data, base + 1)
        if actor or value:
            initiative.append({"slot": slot, "actor": _hex(actor), "value": value})

    base = ACTIVE_ACTION_BASE
    active = {
        "actor": _hex(data[base]),
        "target": _hex(data[base + 2]),
        "command": _hex(data[base + 6]),
        "action": f"{data[base + 11]:02X}{data[base + 10]:02X}",
    }
    return {
        "battle_mode": _hex(data[0x09AA]),
        "ui_token_0b4e": _hex(data[0x0B4E]),
        "input_mode_1f55e": _hex(data[0x1F55E]),
        "target_index_0026": _hex(data[0x0026]),
        "target_flags_0027": _hex(data[0x0027]),
        "formation": formation,
        "party": party_hp,
        "enemies": enemies,
        "commands": commands,
        "initiative": initiative,
        "active": active,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--button", choices=("a", "b", "x", "y", "up", "down", "left", "right"))
    parser.add_argument("--frames", type=int, default=2)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "benchmarks" / "battle_trace.json")
    args = parser.parse_args()

    bridge = MesenFileBridge(timeout=15.0)
    bridge.start()
    started = time.monotonic()
    records = []
    samples = 0
    last = None

    initial = decode(bridge.dump())
    initial["t_ms"] = 0
    records.append(initial)
    last = {key: value for key, value in initial.items() if key != "t_ms"}

    if args.button:
        bridge.pulse(args.button, frames=args.frames, settle_seconds=0)

    deadline = started + max(0.1, args.duration)
    while time.monotonic() < deadline:
        state = decode(bridge.dump())
        samples += 1
        if state != last:
            state["t_ms"] = round((time.monotonic() - started) * 1000)
            records.append(state)
            last = {key: value for key, value in state.items() if key != "t_ms"}

    result = {
        "button": args.button,
        "frames": args.frames if args.button else None,
        "duration_seconds": args.duration,
        "samples": samples,
        "transitions": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{samples} Samples, {len(records)} Zustände: {args.output.resolve()}")
    for record in records:
        print(
            f"{record['t_ms']:>5} ms ui={record['ui_token_0b4e']} "
            f"input={record['input_mode_1f55e']} "
            f"battle={record['battle_mode']} enemies="
            f"{[(enemy['identity'], enemy['hp']) for enemy in record['enemies']]} "
            f"initiative={record['initiative']} active={record['active']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
