"""Render the confirmed Mesen WRAM map buffer around the actor."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.mesen_controller import MesenController
from agent.navigation.tile_buffer import TileBufferRegistry


def render(context: dict) -> str:
    if not context.get("available"):
        return f"Map buffer unavailable: {context.get('reason', 'unknown')}"
    lines = [
        f"scope={context['scope']} center={tuple(context['center_live'])} radius={context['radius']}",
        *context["rows"],
        "cardinal:",
    ]
    for cell in context["cardinal_cells"]:
        lines.append(
            f"  rel={tuple(cell['relative'])} live={tuple(cell['live'])} "
            f"addr={cell['address']} value={cell['value']:02X} "
            f"family={cell['family']} occupied={cell['occupied']}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read a registered live map buffer directly through the Mesen Lua bridge."
    )
    parser.add_argument("--radius", type=int, default=4, choices=range(1, 5))
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=0.4)
    args = parser.parse_args()

    config = json.loads((ROOT / "runtime_config.json").read_text(encoding="utf-8"))
    controller = MesenController(config["emulator"])
    registry = TileBufferRegistry()
    controller.connect()
    try:
        while True:
            observation = controller.observe_stable()
            context = registry.context(
                observation.game.map_id,
                observation.game.x,
                observation.game.y,
                observation.wram,
                radius=args.radius,
            )
            if args.watch:
                print("\x1b[2J\x1b[H", end="")
            print(render(context), flush=True)
            if not args.watch:
                return 0
            time.sleep(max(0.1, args.interval))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
