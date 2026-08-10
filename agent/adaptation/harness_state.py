"""Versioned persistence for non-active shadow proposals."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ShadowHarnessState:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)
        self.directory = self.run_dir / "harness_evolution"
        self.log_path = self.run_dir / "harness_evolution.jsonl"
        self.directory.mkdir(parents=True, exist_ok=True)
        existing = sorted(self.directory.glob("generation_*.json"))
        generations = []
        for path in existing:
            try:
                generations.append(int(path.stem.rsplit("_", 1)[-1]))
            except ValueError:
                continue
        self.generation = max(generations, default=0)

    def last_action_index(self) -> int:
        if not self.log_path.exists():
            return 0
        last = 0
        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    last = max(last, int(value.get("last_action_index", 0)))
        return last

    def write(
        self,
        *,
        trigger: str,
        action_range: list[int] | None,
        status: str,
        proposals: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        self.generation += 1
        record = {
            "schema": "lufia2-shadow-harness-generation-v1",
            "generation": self.generation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "shadow",
            "active": False,
            "trigger": trigger,
            "action_index_range": action_range,
            "last_action_index": action_range[-1] if action_range else 0,
            "status": status,
            "proposals": proposals or {},
            "error": error,
        }
        generation_path = self.directory / f"generation_{self.generation:04d}.json"
        generation_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        return record
