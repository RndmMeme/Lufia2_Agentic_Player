"""Quick journal reader for agent runs."""

import json
import sys

run_dir = sys.argv[1] if len(sys.argv) > 1 else "data/runs/20260803_030521"
path = f"{run_dir}/journal.jsonl"

with open(path, encoding="utf-8") as f:
    for line in f:
        event = json.loads(line)
        ev = event["event"]
        if ev in ("start", "model_intent", "use_tool", "move", "face", "interact",
                  "thinking_gate_rejected", "reasoning_step_limit", "stop",
                  "model_wait_warning", "anti_stall", "look_map", "look"):
            payload = {k: v for k, v in event.items()
                       if k not in ("timestamp", "state", "navigation", "feedback", "evidence", "context_budget", "emulator")}
            print(f"[{ev}] {json.dumps(payload, ensure_ascii=False)[:300]}")
