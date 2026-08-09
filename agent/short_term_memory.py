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
            "room_episode": {
                "generation": 0,
                "origin": "run_start",
                "puzzle_status": "unknown",
                "perception_status": "not_observed",
                "intent_status": "none",
            },
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
        existing_changes = self.state.get("confirmed_world_changes", [])
        existing_changes = [
            change for change in existing_changes
            if change.get("action_kind") != "move"
        ]
        self.state["confirmed_world_changes"] = existing_changes
        if not existing_changes:
            self.state["confirmed_world_changes"] = self._recover_world_changes()
        elif any(
            change.get("source_landmark") == "observed_world_change"
            and "action_kind" not in change
            for change in existing_changes
        ):
            curated = [
                change for change in existing_changes
                if change.get("source_landmark") != "observed_world_change"
            ]
            self.state["confirmed_world_changes"] = (
                curated + self._recover_world_changes()
            )[-4:]

    @staticmethod
    def _world_change_from_action(action: dict, before: dict, after: dict) -> dict | None:
        if action.get("kind") in {"move", "reset_room"}:
            return None
        count = int(action.get("map_tile_change_count", 0))
        if count <= 0:
            return None
        direction = action.get("requested_direction")
        kind = action.get("kind")
        source = before.get("position")
        destination = after.get("position")
        result = {
            "source_landmark": "observed_world_change",
            "source_live": source,
            "action_kind": kind,
            "direction": direction,
            "actor_after": destination,
            "effect": {
                "message": (
                    f"Confirmed {kind}"
                    f"{f' {direction}' if direction else ''} at {source} changed {count} "
                    f"non-actor map tile(s); actor ended at {destination}. Preserve and use "
                    "this resulting puzzle state unless deliberate recovery requires undoing it."
                )
            },
            "changed_live_tiles": [
                change.get("live")
                for change in action.get("map_tile_changes", [])
                if change.get("live")
            ][:12],
            "authority": "confirmed action-linked WRAM map-buffer change",
        }
        direction_delta = {
            "north": (0, -1), "south": (0, 1),
            "west": (-1, 0), "east": (1, 0),
        }.get(direction)
        if (
            kind == "interact"
            and direction_delta
            and isinstance(source, list) and isinstance(destination, list)
            and len(source) == 2 and len(destination) == 2
            and destination == [
                source[0] + direction_delta[0],
                source[1] + direction_delta[1],
            ]
        ):
            result["movable_object_after"] = [
                destination[0] + direction_delta[0],
                destination[1] + direction_delta[1],
            ]
            result["tracking_authority"] = (
                "inferred from a successful directed push and actor displacement"
            )
        return result

    def _recover_world_changes(self) -> list[dict]:
        """Recover current-room effects after a stopped/resumed agent process."""
        journal = self.path.with_name("action_outcomes.jsonl")
        if not journal.exists():
            return []
        changes: list[dict] = []
        try:
            for line in journal.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                action = record.get("action", {})
                navigation = record.get("navigation", {})
                entered_new_room = bool(navigation.get("new_room"))
                if action.get("kind") == "reset_room" or entered_new_room:
                    changes = []
                if entered_new_room:
                    # Transition animation/buffer replacement is not a puzzle
                    # mutation in the newly entered room.
                    continue
                if action.get("kind") == "move":
                    # Ordinary walking can expose different scroll-buffer cells
                    # and look like a semantic mutation in a historical log.
                    # Live movement effects are still retained by record_action.
                    continue
                change = self._world_change_from_action(
                    action, record.get("before", {}), record.get("after", {})
                )
                if change:
                    changes.append(change)
        except (OSError, json.JSONDecodeError):
            return []
        return changes[-4:]

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
        previous_room_id = self.state.get("room", {}).get("id")
        next_room_id = room.get("id")
        if previous_room_id and next_room_id and previous_room_id != next_room_id:
            self.state["confirmed_world_changes"] = []
            self.state["recent_perceptions"] = []
            generation = int(self.state.get("room_episode", {}).get("generation", 0)) + 1
            self.state["room_episode"] = {
                "generation": generation,
                "origin": "room_entry",
                "puzzle_status": "unknown",
                "perception_status": "not_observed",
                "intent_status": "none",
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
        curated_changes = navigation.get("confirmed_world_changes", [])
        if curated_changes:
            existing = self.state.setdefault("confirmed_world_changes", [])
            for change in curated_changes:
                if change not in existing:
                    existing.append(change)
            self.state["confirmed_world_changes"] = existing[-4:]
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
        if action.get("kind") == "reset_room":
            self.state["recent_actions"] = [compact]
            self.state["confirmed_world_changes"] = []
            self.state["recent_perceptions"] = []
            self.state["active_target"] = None
            self.state["room_reset_recovery"] = {"eligible": False}
            generation = int(self.state.get("room_episode", {}).get("generation", 0)) + 1
            self.state["room_episode"] = {
                "generation": generation,
                "origin": "reset_room",
                "puzzle_status": "unsolved",
                "perception_status": "fresh_observation_required",
                "intent_status": "none",
            }
            after = action.get("after", {})
            current = self.state.setdefault("current", {})
            if after.get("position") is not None:
                current["position"] = after.get("position")
            for key in ("direction", "blocked_direction", "mode"):
                if key in after:
                    current[key] = after.get(key)
        else:
            self.state.setdefault("recent_actions", []).append(compact)
            self.state["recent_actions"] = self.state["recent_actions"][-24:]
            episode = self.state.get("room_episode", {})
            if (
                episode.get("origin") in {"reset_room", "external_reset"}
                and episode.get("intent_status") == "none"
            ):
                episode["intent_status"] = "reformed_from_post_reset_live_state"
            change = self._world_change_from_action(
                action, action.get("before", {}), action.get("after", {})
            )
            if change:
                changes = self.state.setdefault("confirmed_world_changes", [])
                changes.append(change)
                self.state["confirmed_world_changes"] = changes[-4:]
        self._save()

    def clear_room_episode(self) -> None:
        """Clear room-local cognition after an already executed external/reset action."""
        self.state["active_target"] = None
        self.state["confirmed_world_changes"] = []
        self.state["room_reset_recovery"] = {"eligible": False}
        self.state["recent_actions"] = []
        self.state["recent_perceptions"] = []
        generation = int(self.state.get("room_episode", {}).get("generation", 0)) + 1
        self.state["room_episode"] = {
            "generation": generation,
            "origin": "external_reset",
            "puzzle_status": "unsolved",
            "perception_status": "fresh_observation_required",
            "intent_status": "none",
        }
        self._save()

    def record_perception(
        self, kind: str, question: str, result: dict, action_count: int | None = None
    ) -> None:
        self.state.setdefault("recent_perceptions", []).append({
            "kind": kind,
            "question": question,
            "result": result,
            "action_count": action_count,
        })
        self.state["recent_perceptions"] = self.state["recent_perceptions"][-6:]
        episode = self.state.get("room_episode", {})
        if episode.get("origin") in {"reset_room", "external_reset"}:
            episode["perception_status"] = "observed_after_reset"
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
            "room_episode": self.state.get("room_episode", {}),
            "active_target": self.state.get("active_target"),
            "selected_tool": self.state.get("selected_tool"),
            "owned_tools": self.state.get("owned_tools", []),
            "confirmed_world_changes": self.state.get("confirmed_world_changes", []),
            "room_reset_recovery": self.state.get("room_reset_recovery", {}),
            "recent_actions": self.state.get("recent_actions", [])[-8:],
            # Internal recovery correlation needs enough history to retain a
            # decisive observation when later looks are empty or ambiguous.
            # This snapshot is not injected wholesale into the normal prompt.
            "recent_perceptions": self.state.get("recent_perceptions", [])[-6:],
            "revision": int(self.state.get("revision", 0)),
        }
