"""Run-local short-term memory kept outside the stateless model prompt."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ShortTermMemory:
    """Persist recent action and puzzle state while exposing only a tiny hint."""

    SCHEMA = "lufia2-short-term-memory-v1"

    def __init__(self, path: Path, goal: str) -> None:
        self.path = path
        self.state = {
            "schema": self.SCHEMA,
            "revision": 0,
            "goal": goal,
            "current": {},
            "room": {},
            "active_target": None,
            "selected_tool": None,
            "owned_tools": [],
            "confirmed_world_changes": [],
            "room_reset_recovery": {"eligible": False},
            "recent_actions": [],
            "recent_perceptions": [],
        }
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if loaded.get("schema") == self.SCHEMA:
                    self.state.update(loaded)
                    self.state["goal"] = goal
            except (OSError, json.JSONDecodeError):
                pass

    def _save(self) -> None:
        self.state["revision"] = int(self.state.get("revision", 0)) + 1
        self.state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.state, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def update_context(self, raw: dict, action_count: int) -> None:
        game = raw.get("game", {})
        navigation = raw.get("navigation", {})
        room = navigation.get("current_room", {})
        self.state["action_count"] = int(action_count)
        self.state["current"] = {
            "map_id": game.get("map_id"),
            "map_name": game.get("map_name"),
            "position": [game.get("x"), game.get("y")],
            "direction": game.get("direction"),
            "blocked_direction": game.get("blocked_direction"),
            "mode": game.get("mode"),
        }
        self.state["room"] = {
            "id": room.get("id"),
            "objective": room.get("objective"),
            "success_evidence": room.get("success_evidence"),
        }
        active = navigation.get("active_landmark") or {}
        self.state["active_target"] = {
            key: active.get(key)
            for key in (
                "id", "live", "effective_live", "kind", "action", "tool", "facing",
                "selection_reason", "traversal", "checkpoint",
            )
            if active.get(key) is not None
        } or None
        self.state["selected_tool"] = raw.get("selected_dungeon_tool")
        self.state["owned_tools"] = [
            item.get("name")
            for item in raw.get("exploration_relevant_items", [])
            if item.get("available")
        ]
        self.state["confirmed_world_changes"] = navigation.get(
            "confirmed_world_changes", []
        )[-4:]
        recovery = raw.get("room_reset_recovery", {})
        self.state["room_reset_recovery"] = (
            recovery if recovery.get("eligible") else {"eligible": False}
        )
        self._save()

    def record_action(self, action: dict) -> None:
        feedback = action.get("feedback", {})
        compact = {
            "kind": action.get("kind"),
            "from": action.get("before", {}).get("position"),
            "to": action.get("after", {}).get("position"),
            "direction": action.get("requested_direction"),
            "tiles": action.get("requested_tiles"),
            "tool": action.get("tool"),
            "blocked_direction": action.get("after", {}).get("blocked_direction"),
            "reward": feedback.get("delta"),
            "outcome": feedback.get("feedback"),
            "semantic_tile_changes": int(action.get("map_tile_change_count", 0)),
            "completed_landmark": (action.get("completed_landmark") or {}).get("landmark_id"),
            "completed_checkpoint": (action.get("completed_checkpoint") or {}).get("id"),
        }
        self.state.setdefault("recent_actions", []).append(compact)
        self.state["recent_actions"] = self.state["recent_actions"][-24:]
        self._save()

    def record_perception(self, kind: str, question: str, result: dict) -> None:
        self.state.setdefault("recent_perceptions", []).append({
            "kind": kind,
            "question": question,
            "result": result,
        })
        self.state["recent_perceptions"] = self.state["recent_perceptions"][-6:]
        self._save()

    def prompt_hint(self) -> dict:
        return {
            "available": True,
            "query": "short term memory",
            "revision": int(self.state.get("revision", 0)),
            "use_when": "Retrieve only when earlier actions or puzzle changes are needed.",
        }

    def recall(self) -> dict:
        return {
            "goal": self.state.get("goal"),
            "current": self.state.get("current", {}),
            "room": self.state.get("room", {}),
            "active_target": self.state.get("active_target"),
            "selected_tool": self.state.get("selected_tool"),
            "owned_tools": self.state.get("owned_tools", []),
            "confirmed_world_changes": self.state.get("confirmed_world_changes", []),
            "room_reset_recovery": self.state.get("room_reset_recovery", {}),
            "recent_actions": self.state.get("recent_actions", [])[-8:],
            "recent_perceptions": self.state.get("recent_perceptions", [])[-2:],
            "revision": int(self.state.get("revision", 0)),
        }
