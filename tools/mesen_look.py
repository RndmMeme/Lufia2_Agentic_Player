#!/usr/bin/env python3
"""Capture an on-demand Mesen visual observation with WRAM and map semantics."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.navigation.online_mapper import LiveNavigationObservation, OnlineNavigationMapper
from wram_discovery.mesen_bridge import MesenBridgeError, MesenFileBridge


DEFAULT_CURATION = (
    PROJECT_ROOT
    / "emulator/maps/Dungeons/Secret_Skills_Cave/navigation/compiled_curation.json"
)


def nearby_curation(path: Path | None, observation: LiveNavigationObservation, radius: int) -> list[dict]:
    if path is None or not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    nearby = []
    for marker in data.get("markers", []):
        anchor = marker.get("anchor") or {}
        if "x" not in anchor or "y" not in anchor:
            continue
        dx = int(anchor["x"]) - observation.x
        dy = int(anchor["y"]) - observation.y
        if abs(dx) <= radius and abs(dy) <= radius:
            nearby.append(
                {
                    "type": marker.get("type"),
                    "traversal": marker.get("traversal"),
                    "required_action": marker.get("required_action"),
                    "notes": marker.get("notes"),
                    "x": int(anchor["x"]),
                    "y": int(anchor["y"]),
                    "dx": dx,
                    "dy": dy,
                    "coordinate": anchor.get("coordinate"),
                }
            )
    return nearby


def nearby_graph(path: Path | None, observation: LiveNavigationObservation, radius: int) -> dict:
    if path is None or not path.exists():
        return {}
    mapper = OnlineNavigationMapper.load(path)
    current_key = mapper.node_key(observation.map_id, observation.x, observation.y)
    unresolved = []
    nearby_node_count = 0
    open_edge_count = 0
    for key, node in mapper.state["nodes"].items():
        if int(node["map_id"]) != observation.map_id:
            continue
        if abs(int(node["x"]) - observation.x) > radius:
            continue
        if abs(int(node["y"]) - observation.y) > radius:
            continue
        nearby_node_count += 1
        for direction, edge in mapper.state["edges"].get(key, {}).items():
            if edge.get("outcome") in {"open", "transition"}:
                open_edge_count += 1
            elif edge.get("outcome") == "blocked_now":
                unresolved.append(
                    {
                        "source": key,
                        "direction": direction,
                        "blocked_byte": edge.get("blocked_byte"),
                        "structural_type": edge.get("structural_type", "unknown"),
                    }
                )
    return {
        "current_node": current_key,
        "current_edges": mapper.state["edges"].get(current_key, {}),
        "nearby_summary": {
            "radius": radius,
            "known_nodes": nearby_node_count,
            "directed_open_edges": open_edge_count,
            "unresolved_collisions": unresolved[:24],
            "unresolved_collision_count": len(unresolved),
        },
    }


def run(args: argparse.Namespace) -> int:
    output = args.output or (
        PROJECT_ROOT / "data/vision_observations" / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    output.mkdir(parents=True, exist_ok=True)
    bridge = MesenFileBridge(timeout=10.0)
    bridge.start()
    if not bridge.wait_attached(timeout=3.0):
        raise TimeoutError("Mesen Lua bridge is not responding.")
    observation = LiveNavigationObservation.from_wram(bridge.dump(), actor_slot=args.actor_slot)
    screenshot = bridge.screenshot()
    image_path = output / "frame.png"
    image_path.write_bytes(screenshot)

    context = {
        "question": args.question,
        "frame": str(image_path),
        "wram": asdict(observation),
        "semantics": {
            "player_anchor": "WRAM x/y is the character's feet/collision anchor, not the sprite head.",
            "collision": (
                "A matching blocked_attempt plus unchanged x/y proves only directed "
                "impassable_now. It does not prove wall, permanence, or reverse blocking."
            ),
            "visual_role": (
                "Use the frame to classify visible semantics such as wall, locked door, "
                "stairs, actor, movable object, switch, hazard, or unknown puzzle state."
            ),
            "authority": "WRAM movement is traversal truth; visual classification is a hypothesis until tested.",
        },
        "nearby_curation": nearby_curation(args.curation, observation, args.radius),
        "nearby_runtime_graph": nearby_graph(args.graph, observation, args.radius),
        "requested_output": {
            "scene_type": "dungeon, battle, menu, dialog, or unknown",
            "relevant_objects": "objects related to the question with relative direction",
            "navigation_hypothesis": "what might be required; include confidence",
            "safe_next_test": "one reversible controller action, or none",
        },
    }
    (output / "context.json").write_text(
        json.dumps(context, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output / "prompt.md").write_text(
        "# On-demand visual observation\n\n"
        f"Question: {args.question}\n\n"
        "Read `context.json` together with `frame.png`. Do not convert a failed movement "
        "into a wall claim unless the image or curated semantics supports that classification.\n",
        encoding="utf-8",
    )
    print(json.dumps(context, indent=2, ensure_ascii=False))
    print(f"Observation bundle: {output}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default="What is relevant to navigation in the current scene?")
    parser.add_argument("--graph", type=Path)
    parser.add_argument("--curation", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--radius", type=int, default=6)
    parser.add_argument("--actor-slot", type=int, default=0)
    args = parser.parse_args()
    try:
        return run(args)
    except (MesenBridgeError, TimeoutError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
