#!/usr/bin/env python3
"""Inspect, promote or roll back project-local continual-harness candidates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.adaptation.global_store import ContinualHarnessStore
from agent.config import load_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "promote", "rollback"))
    parser.add_argument("candidate_id", nargs="?")
    parser.add_argument("--reason", default="manual_review")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "runtime_config.json")
    args = parser.parse_args()
    config = load_config(args.config).get("harness_evolution", {})
    path = Path(config.get("global_state_path", "data/harness/continual_harness.json"))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    store = ContinualHarnessStore(path, config)
    if args.command in {"promote", "rollback"} and not args.candidate_id:
        parser.error(f"{args.command} requires candidate_id")
    if args.command == "promote":
        store.promote(args.candidate_id, args.reason)
    elif args.command == "rollback":
        store.rollback(args.candidate_id, args.reason)
    output = store.summary()
    output["review_queue"] = store.review_queue()
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
