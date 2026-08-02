#!/usr/bin/env python3
"""Passively record WRAM changes during one manually controlled battle round."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from mesen_bridge import MesenBridgeError, MesenFileBridge, WRAM_SIZE


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "mesen_bridge" / "validation" / "gameplay"
WATCH_RANGES = (
    (0x0000, 0x2000),
    (0x1F000, 0x20000),
)
DUNGEON_ACTOR_WATCH_RANGES = (
    (0x0500, 0x0800),
    (0x1200, 0x1280),
    (0x2300, 0x2400),
    (0x2800, 0x2D00),
    (0x3500, 0x3600),
)


def watched_changes(
    before: bytes, after: bytes, watch_ranges=WATCH_RANGES
) -> list[list[int]]:
    changes = []
    for start, end in watch_ranges:
        changes.extend(
            [offset, before[offset], after[offset]]
            for offset in range(start, end)
            if before[offset] != after[offset]
        )
    return changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=35.0)
    parser.add_argument("--label", default="enemy_defend_round")
    parser.add_argument(
        "--profile",
        choices=("battle", "dungeon-actor"),
        default="battle",
    )
    parser.add_argument(
        "--press",
        choices=("up", "down", "left", "right"),
        help="Optional direction pulse immediately after the baseline dump.",
    )
    parser.add_argument("--press-frames", type=int, default=2)
    args = parser.parse_args()
    watch_ranges = (
        DUNGEON_ACTOR_WATCH_RANGES
        if args.profile == "dungeon-actor"
        else WATCH_RANGES
    )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    bridge = MesenFileBridge(timeout=10.0)
    bridge.start()
    baseline = bridge.dump()
    if len(baseline) != WRAM_SIZE:
        raise RuntimeError(f"invalid baseline size {len(baseline)}")

    started = time.monotonic()
    previous = baseline
    events = []
    samples = 0
    transient_errors = 0
    if args.press:
        bridge.pulse(args.press, frames=args.press_frames, settle_seconds=0)
    while time.monotonic() - started < args.seconds:
        try:
            current = bridge.dump()
        except (OSError, TimeoutError, MesenBridgeError):
            transient_errors += 1
            time.sleep(0.05)
            continue
        samples += 1
        changes = watched_changes(previous, current, watch_ranges)
        if changes:
            events.append({
                "t": round(time.monotonic() - started, 4),
                "changes": changes,
            })
        previous = current

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{args.label}_{stamp}"
    (OUTPUT / f"{stem}_before.bin").write_bytes(baseline)
    (OUTPUT / f"{stem}_after.bin").write_bytes(previous)
    payload = {
        "label": args.label,
        "duration_seconds": round(time.monotonic() - started, 3),
        "samples": samples,
        "transient_errors": transient_errors,
        "press": args.press,
        "press_frames": args.press_frames if args.press else None,
        "watch_ranges": [
            [f"0x{a:05X}", f"0x{b - 1:05X}"] for a, b in watch_ranges
        ],
        "events": events,
    }
    path = OUTPUT / f"{stem}_events.json"
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(path)
    print(f"samples={samples} events={len(events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
