#!/usr/bin/env python3
"""Safely explore a dungeon through Mesen and persist a WRAM-truth graph."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.navigation.online_mapper import LiveNavigationObservation, OnlineNavigationMapper
from agent.perception import KeyframeObserver
from wram_discovery.mesen_bridge import MesenBridgeError, MesenFileBridge

DEFAULT_OBJECTIVE = PROJECT_ROOT / "data" / "navigation_objectives" / "secret_skills_cave_room_sweep.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "online_maps"
MESEN_BUTTON = {"north": "up", "south": "down", "west": "left", "east": "right"}


def read_observation(bridge: MesenFileBridge, actor_slot: int = 0) -> LiveNavigationObservation:
    return LiveNavigationObservation.from_wram(bridge.dump(), actor_slot=actor_slot)


def wait_for_stable_observation(
    bridge: MesenFileBridge,
    actor_slot: int = 0,
    timeout: float = 2.0,
) -> LiveNavigationObservation:
    deadline = time.monotonic() + timeout
    previous = None
    stable_reads = 0
    latest = read_observation(bridge, actor_slot)
    while time.monotonic() < deadline:
        latest = read_observation(bridge, actor_slot)
        signature = (latest.map_id, latest.x, latest.y, latest.movement_state, latest.battle_mode)
        if signature == previous and not latest.moving:
            stable_reads += 1
            if stable_reads >= 1:
                return latest
        else:
            stable_reads = 0
        previous = signature
        if latest.in_battle:
            return latest
        time.sleep(0.04)
    return latest


def save_run_artifacts(mapper: OnlineNavigationMapper, run_dir: Path, map_id: int) -> None:
    mapper.save(run_dir / "online_navigation_graph.json")
    (run_dir / "online_navigation_map.txt").write_text(
        mapper.render_ascii(map_id) + "\n", encoding="utf-8"
    )
    (run_dir / "progress.json").write_text(
        json.dumps(mapper.progress(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> int:
    objective = json.loads(args.objective.read_text(encoding="utf-8"))
    allowed_maps = {int(value) for value in objective.get("allowed_map_ids", [])}
    run_dir = args.output or (
        DEFAULT_OUTPUT_ROOT / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_secret_skills_room_sweep"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    mapper = OnlineNavigationMapper.load(args.resume) if args.resume else OnlineNavigationMapper(objective)
    keyframes = KeyframeObserver(run_dir, min_action_gap=args.visual_gap)
    bridge = MesenFileBridge(timeout=10.0)
    bridge.start()
    if not bridge.wait_attached(timeout=3.0):
        raise TimeoutError("Mesen Lua bridge is not responding.")

    observation = wait_for_stable_observation(bridge, actor_slot=args.actor_slot)
    if observation.in_battle:
        raise RuntimeError("Refusing to start room sweep while battle mode is active.")
    if allowed_maps and observation.map_id not in allowed_maps:
        raise RuntimeError(
            f"Current map 0x{observation.map_id:02X} is outside allowed maps "
            f"{sorted(f'0x{x:02X}' for x in allowed_maps)}."
        )
    _, first_room = mapper.observe(observation)
    if first_room and args.screenshots:
        (run_dir / f"{mapper.room_for(observation)}_first.png").write_bytes(bridge.screenshot())
    save_run_artifacts(mapper, run_dir, observation.map_id)

    print(
        f"LIVE map=0x{observation.map_id:02X} pos=({observation.x},{observation.y}) "
        f"room={mapper.room_for(observation)} dir=0x{observation.direction:02X}"
    )
    print(json.dumps(mapper.progress(), ensure_ascii=False))
    if not args.execute:
        print(f"DRY RUN: next={mapper.next_direction()} output={run_dir}")
        return 0

    started = time.monotonic()
    stop_reason = "action_limit"
    while mapper.state.get("action_count", 0) < args.max_actions:
        if time.monotonic() - started >= args.max_minutes * 60:
            stop_reason = "time_limit"
            break
        if mapper.progress()["complete"]:
            stop_reason = "objective_complete"
            break
        planned_move = mapper.next_move(exploration_distance=args.frontier_tiles)
        if planned_move is None:
            stop_reason = "no_reachable_frontier"
            break
        direction, requested_tiles, movement_reason = planned_move

        before = observation
        frames = args.pulse_frames or (args.frames_per_tile * requested_tiles)
        bridge.pulse(
            MESEN_BUTTON[direction],
            frames=frames,
            settle_seconds=args.settle_seconds,
        )
        observation = wait_for_stable_observation(bridge, actor_slot=args.actor_slot)
        event = mapper.record_move(before, direction, observation)
        print(
            f"#{mapper.state['action_count']:04d} {direction:<5} "
            f"({before.x},{before.y})->({observation.x},{observation.y}) "
            f"{event['outcome']} requested={requested_tiles}tile/{frames}f "
            f"reason={movement_reason} blocked=0x{observation.blocked_attempt:02X}"
        )

        if event["new_room"] and args.screenshots:
            room = mapper.room_for(observation)
            (run_dir / f"{room}_first.png").write_bytes(bridge.screenshot())
        if args.visual_keyframes and (
            event["new_room"]
            or event["outcome"] in {"blocked_now", "transition", "encounter"}
        ):
            queued = keyframes.capture(event, bridge.screenshot())
            if queued:
                print(f"       visual-keyframe={queued['reason']} -> {queued['image']}")
        save_run_artifacts(mapper, run_dir, observation.map_id)

        if observation.in_battle:
            stop_reason = "battle_detected"
            break
        if allowed_maps and observation.map_id not in allowed_maps:
            stop_reason = f"left_allowed_map_to_0x{observation.map_id:02X}"
            break

    summary = {
        "stop_reason": stop_reason,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        **mapper.progress(),
    }
    (run_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Artifacts: {run_dir}")
    return 0 if stop_reason in {"objective_complete", "action_limit", "time_limit", "battle_detected"} else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objective", type=Path, default=DEFAULT_OBJECTIVE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--actor-slot", type=int, default=0)
    parser.add_argument("--max-actions", type=int, default=40)
    parser.add_argument("--max-minutes", type=float, default=3.0)
    parser.add_argument(
        "--pulse-frames",
        type=int,
        help="Compatibility override: fixed hold length for every movement.",
    )
    parser.add_argument("--frames-per-tile", type=int, default=6)
    parser.add_argument("--frontier-tiles", type=int, default=2)
    parser.add_argument("--settle-seconds", type=float, default=0.32)
    parser.add_argument("--screenshots", action="store_true")
    parser.add_argument(
        "--visual-keyframes",
        action="store_true",
        help="Queue sparse event-driven screenshots for asynchronous VLM analysis.",
    )
    parser.add_argument("--visual-gap", type=int, default=4)
    parser.add_argument("--execute", action="store_true", help="Actually send directional inputs to Mesen.")
    args = parser.parse_args()
    try:
        return run(args)
    except (MesenBridgeError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
