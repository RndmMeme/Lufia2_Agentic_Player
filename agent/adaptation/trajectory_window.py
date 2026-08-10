"""Build a bounded refinement window from existing run artifacts."""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any


class TrajectoryWindow:
    """Read-only view over the latest replay-friendly run evidence."""

    def __init__(
        self,
        run_dir: Path,
        max_actions: int = 24,
        max_journal_events: int = 24,
    ) -> None:
        self.run_dir = Path(run_dir)
        self.max_actions = max(1, int(max_actions))
        self.max_journal_events = max(1, int(max_journal_events))

    @staticmethod
    def _jsonl_tail(path: Path, limit: int) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        records: deque[dict[str, Any]] = deque(maxlen=max(1, limit))
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    records.append(value)
        return list(records)

    @staticmethod
    def _json_object(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return value if isinstance(value, dict) else {}

    def action_records(self) -> list[dict[str, Any]]:
        return self._jsonl_tail(
            self.run_dir / "action_outcomes.jsonl", self.max_actions
        )

    @staticmethod
    def _compact_action(record: dict[str, Any]) -> dict[str, Any]:
        action = record.get("action", {})
        tile_diff = record.get("tile_diff", {})
        return {
            "index": record.get("index"),
            "action": {
                key: action.get(key)
                for key in (
                    "kind", "requested_direction", "requested_tiles", "tool",
                    "completed_checkpoint", "completed_landmark",
                    "navigation_relevant_change", "immediate_backtrack",
                )
                if action.get(key) is not None
            },
            "before": record.get("before", {}),
            "after": record.get("after", {}),
            "navigation": record.get("navigation", {}),
            "tile_diff": {
                "available": tile_diff.get("available", False),
                "count": tile_diff.get("count", 0),
                "semantic_count": tile_diff.get("semantic_count", 0),
                "changes": [
                    {
                        key: change.get(key)
                        for key in ("live", "before", "after", "family")
                        if change.get(key) is not None
                    }
                    for change in tile_diff.get("changes", [])[:8]
                    if isinstance(change, dict)
                ],
            },
            "feedback": record.get("feedback", {}),
        }

    @staticmethod
    def detect_trigger(records: list[dict[str, Any]]) -> str | None:
        """Return an evidence-derived refinement reason, never a game action."""
        if not records:
            return None
        latest = records[-1]
        action = latest.get("action", {})
        navigation = latest.get("navigation", {})
        if action.get("completed_checkpoint") or action.get("completed_landmark"):
            return "milestone_completed"
        if navigation.get("new_room"):
            return "room_transition"
        if latest.get("before", {}).get("mode") != latest.get("after", {}).get("mode"):
            return "mode_transition"

        positions = [
            tuple(record.get("after", {}).get("position", []))
            for record in records[-4:]
        ]
        if (
            len(positions) == 4
            and len(positions[0]) == 2
            and positions[0] == positions[2]
            and positions[1] == positions[3]
            and positions[0] != positions[1]
        ):
            return "repeated_navigation_loop"

        stalled = records[-3:]
        if len(stalled) == 3 and all(
            record.get("before", {}).get("position")
            == record.get("after", {}).get("position")
            and int(record.get("feedback", {}).get("delta", 0)) <= 0
            for record in stalled
        ):
            return "repeated_no_progress_actions"
        return None

    def build(self, trigger: str) -> dict[str, Any]:
        actions = self.action_records()
        journal = self._jsonl_tail(
            self.run_dir / "journal.jsonl", self.max_journal_events
        )
        compact_journal = [
            {
                key: event.get(key)
                for key in (
                    "timestamp", "event", "action", "direction", "tool",
                    "result", "stop_reason", "intent", "navigation_event",
                    "elapsed_seconds",
                )
                if event.get(key) is not None
            }
            for event in journal
        ]
        memory = self._json_object(self.run_dir / "short_term_memory.json")
        compact_memory = {
            "goal": memory.get("goal"),
            "room_episode": memory.get("room_episode"),
            "current_objective": memory.get("current_objective"),
            "confirmed_world_changes": memory.get("confirmed_world_changes", [])[-4:],
            "recent_actions": memory.get("recent_actions", [])[-6:],
        }
        compact_memory = {
            key: value for key, value in compact_memory.items()
            if value not in (None, [], {})
        }
        prompt_stats = self._jsonl_tail(
            self.run_dir / "prompt_stats.jsonl", 6
        )
        indices = [
            int(record["index"])
            for record in actions
            if isinstance(record.get("index"), int)
        ]
        return {
            "schema": "lufia2-harness-refinement-window-v1",
            "trigger": trigger,
            "action_index_range": (
                [min(indices), max(indices)] if indices else None
            ),
            "actions": [self._compact_action(record) for record in actions],
            "journal_events": compact_journal,
            "short_term_memory": compact_memory,
            "prompt_stats": prompt_stats,
        }
