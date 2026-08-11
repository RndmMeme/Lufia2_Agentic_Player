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
        max_chars: int = 9000,
    ) -> None:
        self.run_dir = Path(run_dir)
        self.max_actions = max(1, int(max_actions))
        self.max_journal_events = max(1, int(max_journal_events))
        self.max_chars = max(3000, int(max_chars))

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
        checkpoint = action.get("completed_checkpoint")
        if isinstance(checkpoint, dict):
            checkpoint = checkpoint.get("id") or checkpoint.get("landmark")
        landmark = action.get("completed_landmark")
        if isinstance(landmark, dict):
            landmark = landmark.get("id")

        def compact_state(value: Any) -> dict[str, Any]:
            value = value if isinstance(value, dict) else {}
            return {
                key: value.get(key)
                for key in (
                    "map_id", "position", "direction", "blocked_direction", "mode",
                    "event_flags_digest", "dungeon_flags_digest",
                )
                if value.get(key) is not None
            }

        navigation = record.get("navigation", {})
        feedback = record.get("feedback", {})
        return {
            "index": record.get("index"),
            "action": {
                **{
                    key: action.get(key)
                    for key in (
                        "kind", "requested_direction", "requested_tiles", "tool",
                        "navigation_relevant_change", "immediate_backtrack",
                    )
                    if action.get(key) is not None
                },
                **({"completed_checkpoint": checkpoint} if checkpoint else {}),
                **({"completed_landmark": landmark} if landmark else {}),
            },
            "before": compact_state(record.get("before")),
            "after": compact_state(record.get("after")),
            "navigation": {
                key: navigation.get(key)
                for key in ("outcome", "new_room", "direction", "source", "target")
                if navigation.get(key) is not None
            },
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
                    for change in tile_diff.get("changes", [])[:4]
                    if isinstance(change, dict)
                ],
            },
            "feedback": {
                "delta": feedback.get("delta", 0),
                "message": str(feedback.get("message", ""))[:240],
            },
        }

    @staticmethod
    def _compact_journal_event(event: dict[str, Any]) -> dict[str, Any]:
        intent = event.get("intent")
        compact_intent = None
        if isinstance(intent, dict):
            compact_intent = {
                key: intent.get(key)
                for key in ("kind", "direction", "count", "tool")
                if intent.get(key) is not None
            }
            if intent.get("rationale"):
                compact_intent["rationale"] = str(intent["rationale"])[:180]
        navigation = event.get("navigation_event")
        compact_navigation = None
        if isinstance(navigation, dict):
            compact_navigation = {
                key: navigation.get(key)
                for key in ("outcome", "new_room", "direction", "source", "target")
                if navigation.get(key) is not None
            }
        return {
            **{
                key: event.get(key)
                for key in (
                    "timestamp", "event", "action", "direction", "tool",
                    "result", "stop_reason", "elapsed_seconds",
                )
                if event.get(key) is not None
            },
            **({"intent": compact_intent} if compact_intent else {}),
            **({"navigation_event": compact_navigation} if compact_navigation else {}),
        }

    @staticmethod
    def _serialized_chars(value: dict[str, Any]) -> int:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))

    def _fit_budget(self, evidence: dict[str, Any]) -> dict[str, Any]:
        """Trim duplicate/old evidence until the real serialized payload fits."""
        # Reserve space for the budget metadata added after trimming.
        content_target = max(2500, self.max_chars - 200)
        while self._serialized_chars(evidence) > content_target:
            if len(evidence.get("journal_events", [])) > 4:
                evidence["journal_events"].pop(0)
                continue
            if len(evidence.get("actions", [])) > 8:
                evidence["actions"].pop(0)
                continue
            if evidence.get("prompt_stats"):
                evidence["prompt_stats"].pop(0)
                continue
            memory = evidence.get("short_term_memory", {})
            if memory.get("confirmed_world_changes"):
                memory["confirmed_world_changes"].pop(0)
                continue
            if "current_objective" in memory:
                memory.pop("current_objective")
                continue
            break
        indices = [
            int(record["index"])
            for record in evidence.get("actions", [])
            if isinstance(record.get("index"), int)
        ]
        evidence["action_index_range"] = (
            [min(indices), max(indices)] if indices else None
        )
        evidence["payload_budget"] = {
            "max_chars": self.max_chars,
            "serialized_chars": 0,
        }
        evidence["payload_budget"]["serialized_chars"] = self._serialized_chars(evidence)
        return evidence

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
        compact_journal = [self._compact_journal_event(event) for event in journal]
        memory = self._json_object(self.run_dir / "short_term_memory.json")
        compact_memory = {
            "goal": str(memory.get("goal", ""))[:500] or None,
            "current": memory.get("current"),
            "room": memory.get("room"),
            "room_episode": memory.get("room_episode"),
            "current_objective": memory.get("current_objective"),
            "confirmed_world_changes": memory.get("confirmed_world_changes", [])[-2:],
        }
        compact_memory = {
            key: value for key, value in compact_memory.items()
            if value not in (None, [], {})
        }
        prompt_stats = [
            {
                key: record.get(key)
                for key in ("timestamp", "stage", "chars", "estimated_tokens", "compacted")
                if record.get(key) is not None
            }
            for record in self._jsonl_tail(self.run_dir / "prompt_stats.jsonl", 2)
        ]
        indices = [
            int(record["index"])
            for record in actions
            if isinstance(record.get("index"), int)
        ]
        current = memory.get("current", {}) if isinstance(memory.get("current"), dict) else {}
        room = memory.get("room", {}) if isinstance(memory.get("room"), dict) else {}
        map_name = str(current.get("map_name", "")).strip()
        room_id = str(room.get("id") or "").strip()
        allowed_scopes = [
            "global", "exploration", "battle", "dialog",
            "exploration/navigation", "exploration/puzzle",
            "battle/tactics", "dialog/progression",
        ]
        if map_name:
            allowed_scopes.append(f"map:{map_name.lower()}")
            if room_id:
                allowed_scopes.append(f"room:{map_name.lower()}/{room_id.lower()}")
        evidence = {
            "schema": "lufia2-harness-refinement-window-v1",
            "trigger": trigger,
            "action_index_range": (
                [min(indices), max(indices)] if indices else None
            ),
            "actions": [self._compact_action(record) for record in actions],
            "journal_events": compact_journal,
            "short_term_memory": compact_memory,
            "prompt_stats": prompt_stats,
            "scope_context": {
                "map_id": current.get("map_id"),
                "map_name": map_name or None,
                "room_id": room_id or None,
                "allowed_scopes": allowed_scopes,
            },
        }
        return self._fit_budget(evidence)
