#!/usr/bin/env python3
"""Run bounded agent cycles for an unattended learning session."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import PROJECT_ROOT
from agent.session_supervisor import LongSessionSupervisor
from agent.session_supervisor import STOP_REQUEST_PATH, SUPERVISOR_LOCK_PATH
from run_agent import exclusive_file_lock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=float, required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--session-dir", type=Path)
    parser.add_argument("--cycle-minutes", type=float, default=15)
    parser.add_argument("--cycle-actions", type=int, default=400)
    parser.add_argument("--max-unchanged-cycles", type=int, default=4)
    parser.add_argument("--retry-failures", type=int, default=3)
    parser.add_argument("--continue-after-objective", action="store_true")
    parser.add_argument("--recovery", choices=("slot3", "pause"), default="slot3")
    parser.add_argument("--recovery-pause-seconds", type=float, default=30)
    args = parser.parse_args()
    session_dir = args.session_dir or (
        PROJECT_ROOT / "data" / "runs" / f"long_{datetime.now():%Y%m%d_%H%M%S}"
    )
    supervisor = LongSessionSupervisor(
        PROJECT_ROOT,
        session_dir,
        args.goal,
        args.hours,
        cycle_minutes=args.cycle_minutes,
        cycle_actions=args.cycle_actions,
        max_unchanged_cycles=args.max_unchanged_cycles,
        retry_failures=args.retry_failures,
        continue_after_objective=args.continue_after_objective,
        recovery_mode=args.recovery,
        recovery_pause_seconds=args.recovery_pause_seconds,
    )
    try:
        with exclusive_file_lock(
            SUPERVISOR_LOCK_PATH,
            "Another long-session supervisor is already running",
        ):
            STOP_REQUEST_PATH.unlink(missing_ok=True)
            result = supervisor.run()
    except KeyboardInterrupt:
        print("Interrupted by user; the active run_agent child receives normal console termination.")
        return 130
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") in {
        "complete", "time_budget_complete", "operator_stopped"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
