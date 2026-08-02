"""Concise action/outcome evidence independent of verbose run journals."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path


class ActionOutcomeRecorder:
    """Append one small, replay-friendly record for each emulator mutation."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.index = 0
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                self.index = sum(1 for line in handle if line.strip())

    @staticmethod
    def _state(observation) -> dict:
        game = observation.game
        def digest(value: str) -> str:
            return hashlib.sha1(value.encode("ascii")).hexdigest()[:12]

        return {
            "map_id": game.map_id,
            "position": [game.x, game.y],
            "direction": game.direction,
            "blocked_direction": game.blocked_direction,
            "mode": game.mode,
            "event_flags_digest": digest(game.event_flags),
            "dungeon_flags_digest": digest(game.dungeon_flags),
        }

    def record(
        self,
        kind: str,
        before,
        after,
        feedback: dict,
        navigation_event: dict | None = None,
        tile_diff: dict | None = None,
        **details,
    ) -> dict:
        self.index += 1
        record = {
            "schema": "lufia2-action-outcome-v1",
            "index": self.index,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": {"kind": kind, **details},
            "before": self._state(before),
            "after": self._state(after),
            "navigation": {
                key: navigation_event.get(key)
                for key in ("outcome", "new_room", "direction", "source", "target")
                if navigation_event and key in navigation_event
            },
            "tile_diff": tile_diff or {"available": False, "count": 0, "changes": []},
            "feedback": {
                "delta": feedback.get("delta", 0),
                "score_after": feedback.get("score_after", 0),
                "message": feedback.get("feedback", ""),
            },
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        return record
