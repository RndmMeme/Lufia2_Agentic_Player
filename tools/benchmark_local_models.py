#!/usr/bin/env python3
"""Benchmark local multimodal models against the actual bounded agent contract."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import PROJECT_ROOT, load_config
from agent.game_state import GameState
from agent.model_client import LocalModelClient
from wram_discovery.mesen_bridge import MesenFileBridge


DEFAULT_MODELS = (
    "gemma3:4b",
    "hf.co/unsloth/gemma-4-E2B-it-GGUF:UD-Q4_K_XL",
    "hf.co/unsloth/gemma-4-12B-it-qat-GGUF:UD-Q4_K_XL",
)


def context(mode="exploration", blocked=None, suggested="east", enemies=None):
    return {
        "goal": "Finish the randomized game quickly and safely.",
        "game": {
            "map_id": 5,
            "map_name": "Secret Skills Cave",
            "position": [28, 42],
            "direction": "north",
            "blocked_direction": blocked,
            "mode": mode,
            "dialog_active": mode == "dialog",
            "party": [{"name": "Guy", "status": 0, "hp": 747}],
            "enemies": enemies or [],
            "progression_items": ["Bomb", "Hook", "Hammer"],
        },
        "navigation": {
            "unknown_directions": [suggested] if suggested else [],
            "suggested_direction": suggested,
            "policy": "A blocked_now direction must not be retried without new evidence.",
        },
        "strategic_progression": {"goal": "explore current dungeon"},
        "dungeon_context": {"dungeon": "Secret Skills Cave", "coordinate_semantics_available": True},
        "episode_summary": {"recent_outcomes": []},
        "recent_events": [],
        "reasoning_evidence": [],
    }


CASES = (
    ("corridor", context(suggested="east"), lambda value: value.kind == "move" and value.direction == "east"),
    ("blocked_redirect", context(blocked="east", suggested="west"), lambda value: value.kind == "move" and value.direction == "west"),
    ("dialog", context(mode="dialog", suggested=None), lambda value: value.kind == "interact"),
    (
        "battle",
        context(mode="battle", suggested=None, enemies=[{"slot": 0, "id": 0x16, "hp": 100, "status": 0}]),
        lambda value: value.kind == "battle_attack",
    ),
)


def unload(base_url: str, model: str) -> None:
    try:
        requests.post(
            base_url.rstrip("/") + "/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=30,
        ).raise_for_status()
    except requests.RequestException:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--skip-vision", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    config = load_config()["llm"]
    bridge = MesenFileBridge()
    frame = None
    live_context = context()
    if not args.skip_vision:
        bridge.start()
        if not bridge.wait_attached(timeout=3):
            raise RuntimeError("Mesen bridge is required for the vision benchmark")
        frame = PROJECT_ROOT / "data" / "benchmarks" / "current_mesen_frame.png"
        frame.parent.mkdir(parents=True, exist_ok=True)
        wram = bridge.dump()
        frame.write_bytes(bridge.screenshot())
        live = GameState.from_wram(wram).compact()
        live_context = context(
            mode=live["mode"],
            blocked=live["blocked_direction"],
            suggested=None,
            enemies=live["enemies"],
        )
        live_context["game"].update({
            "map_id": live["map_id"],
            "map_name": live["map_name"],
            "position": [live["x"], live["y"]],
            "direction": live["direction"],
            "progression_items": live["progression_items"],
        })

    report = {
        "timestamp": datetime.now().isoformat(),
        "contract": "schema-bound intents plus one gated Mesen screenshot",
        "models": [],
    }
    for model in args.models:
        model_config = dict(config)
        model_config.update({
            "provider": "ollama",
            "planner_model": model,
            "vision_model": model,
            "planner_keep_alive": "2m",
            "vision_keep_alive": "2m",
        })
        client = LocalModelClient(model_config)
        record = {"model": model, "planner": [], "vision": None}
        for name, state, predicate in CASES:
            started = time.monotonic()
            try:
                intent = client.choose_intent(state, max_move_batch=4)
                elapsed = time.monotonic() - started
                record["planner"].append({
                    "case": name,
                    "passed": bool(predicate(intent)),
                    "intent": intent.__dict__,
                    "seconds": round(elapsed, 3),
                })
            except Exception as exc:
                record["planner"].append({
                    "case": name, "passed": False, "error": str(exc),
                    "seconds": round(time.monotonic() - started, 3),
                })
        if frame is not None:
            started = time.monotonic()
            try:
                result = client.look(
                    frame,
                    live_context,
                    "Describe the visible room and only navigation-relevant objects near the player.",
                )
                required = {"scene_type", "relevant_objects", "navigation_hypothesis", "confidence", "safe_next_test"}
                record["vision"] = {
                    "passed_schema": required <= set(result),
                    "result": result,
                    "seconds": round(time.monotonic() - started, 3),
                }
            except Exception as exc:
                record["vision"] = {
                    "passed_schema": False,
                    "error": str(exc),
                    "seconds": round(time.monotonic() - started, 3),
                }
        record["planner_passes"] = sum(item["passed"] for item in record["planner"])
        report["models"].append(record)
        unload("http://127.0.0.1:11434", model)

    output = args.output or (
        PROJECT_ROOT / "data" / "benchmarks" / f"local_models_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Benchmark report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
