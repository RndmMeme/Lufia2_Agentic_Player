#!/usr/bin/env python3
"""Entry point for the bounded Mesen-only Lufia II agent."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from agent.config import PROJECT_ROOT, load_config
from agent.orchestrator import MesenOrchestrator
from wram_discovery.mesen_bridge import MesenBridgeError


RUN_STATE_FILES = (
    "journal.jsonl", "online_navigation_graph.json", "short_term_memory.json",
)


def validate_run_directory(run_dir: Path, resume: bool) -> None:
    existing_state = [name for name in RUN_STATE_FILES if (run_dir / name).exists()]
    if existing_state and not resume:
        raise ValueError(
            f"Run directory already contains state ({', '.join(existing_state)}). "
            "Use a new --run-dir, or pass --resume-run only for an intentional continuation."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal", default="Finish the randomized game as quickly as safely possible.")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "runtime_config.json")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument(
        "--resume-run", action="store_true",
        help="Intentionally reuse mapper and short-term memory from an existing run directory.",
    )
    parser.add_argument("--execute", action="store_true", help="Actually send controller input to Mesen.")
    parser.add_argument("--enable-llm", action="store_true")
    parser.add_argument(
        "--enable-battle",
        action="store_true",
        help="Enable the verified battle coordinator (also requires --enable-llm).",
    )
    parser.add_argument(
        "--resume-battle-stage",
        choices=("pre_menu", "action_cross", "results"),
        help="Explicitly declare the visible UI stage when starting inside a battle.",
    )
    parser.add_argument(
        "--resume-battle-actor",
        type=int,
        choices=range(4),
        default=0,
        metavar="0..3",
    )
    parser.add_argument("--max-actions", type=int)
    parser.add_argument("--max-minutes", type=float)
    args = parser.parse_args()
    config = load_config(args.config)
    if args.enable_llm:
        config["llm"]["enabled"] = True
    if args.enable_battle:
        config.setdefault("battle", {})["execution_enabled"] = True
    if args.max_actions is not None:
        if args.max_actions < 1:
            parser.error("--max-actions must be positive")
        config["limits"]["max_actions_per_run"] = args.max_actions
    if args.max_minutes is not None:
        if args.max_minutes <= 0:
            parser.error("--max-minutes must be positive")
        config["limits"]["max_minutes_per_run"] = args.max_minutes
    run_dir = args.run_dir or (
        PROJECT_ROOT / "data/runs" / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    try:
        validate_run_directory(run_dir, args.resume_run)
        summary = MesenOrchestrator(
            config,
            args.goal,
            run_dir,
            execute=args.execute,
            resume_battle_stage=args.resume_battle_stage,
            resume_battle_actor=args.resume_battle_actor,
        ).run()
    except (MesenBridgeError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    # Keep console output compatible with legacy Windows code pages. The
    # persisted summary remains UTF-8 and human-readable.
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    print(f"Run directory: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
