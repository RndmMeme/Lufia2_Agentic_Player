"""Bounded context memory and drift gates for local model decisions."""

from __future__ import annotations

import json
import hashlib
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from agent.intent import Intent, gate_intent


class ModelDriftError(RuntimeError):
    pass


class ContextHarness:
    """Keep full evidence on disk while sending only decision-relevant state."""

    def __init__(self, config: dict, run_dir: Path):
        self.max_chars = int(config.get("max_prompt_chars", 9000))
        self.summary_path = run_dir / "context_summary.json"
        self.summary = {
            "schema": 1,
            "maps_seen": [],
            "progression_items": [],
            "recent_outcomes": [],
            "blocked_counts": {},
            "compactions": 0,
        }
        if self.summary_path.exists():
            self.summary.update(json.loads(self.summary_path.read_text(encoding="utf-8")))

    @staticmethod
    def _game(game: dict) -> dict:
        party = [
            {
                "name": member.get("name"),
                "status": member.get("status"),
                "hp": member.get("hp"),
                "max_hp": member.get("max_hp"),
                "mp": member.get("mp"),
                "ip": member.get("ip"),
            }
            for member in game.get("party", [])
        ]
        enemies = [
            {
                "slot": enemy.get("slot"),
                "id": enemy.get("identity"),
                "hp": enemy.get("hp"),
                "status": enemy.get("status"),
            }
            for enemy in game.get("enemies", [])
        ]
        def digest(value: str | None) -> str | None:
            if not value:
                return None
            return hashlib.sha1(value.encode("ascii")).hexdigest()[:12]

        return {
            "map_id": game.get("map_id"),
            "map_name": game.get("map_name"),
            "zone_name": game.get("zone_name"),
            "position": [game.get("x"), game.get("y")],
            "direction": game.get("direction"),
            "blocked_direction": game.get("blocked_direction"),
            "mode": game.get("mode"),
            "dialog_active": game.get("dialog_active"),
            "gold": game.get("gold"),
            "party": party,
            "enemies": enemies,
            "progression_items": game.get("progression_items", []),
            "event_flags_digest": digest(game.get("event_flags")),
            "dungeon_flags_digest": digest(game.get("dungeon_flags")),
        }

    @staticmethod
    def _event(event: dict) -> dict:
        allowed = (
            "type", "outcome", "direction", "from", "to", "new_room", "room",
            "map_id", "x", "y",
        )
        return {key: event[key] for key in allowed if key in event}

    def compact(self, raw: dict) -> dict:
        game = self._game(raw["game"])
        map_id = game.get("map_id")
        if map_id is not None and map_id not in self.summary["maps_seen"]:
            self.summary["maps_seen"].append(map_id)
        self.summary["progression_items"] = sorted(set(game.get("progression_items", [])))

        events = [self._event(event) for event in raw.get("recent_events", [])[-6:]]
        for event in events:
            if event.get("outcome"):
                self.summary["recent_outcomes"].append(event)
            if event.get("outcome") == "blocked_now":
                key = f"{event.get('from')}:{event.get('direction')}"
                self.summary["blocked_counts"][key] = self.summary["blocked_counts"].get(key, 0) + 1
        self.summary["recent_outcomes"] = self.summary["recent_outcomes"][-12:]
        self.summary["compactions"] = int(self.summary.get("compactions", 0)) + 1

        dungeon = raw.get("dungeon_context", {})
        if isinstance(dungeon, dict):
            dungeon = {
                "registered": dungeon.get("registered"),
                "dungeon": dungeon.get("dungeon"),
                "coordinate_semantics_available": dungeon.get("coordinate_semantics_available"),
                "nearby_markers": dungeon.get("nearby_markers", [])[:12],
                "warning": dungeon.get("warning"),
            }
        navigation_map = raw.get("navigation_map", {})
        if isinstance(navigation_map, dict):
            navigation_map = dict(navigation_map)
            navigation_map["nearby_curated_markers"] = navigation_map.get("nearby_curated_markers", [])[:10]
        tile_buffer = raw.get("tile_buffer", {})
        if isinstance(tile_buffer, dict):
            tile_buffer = dict(tile_buffer)
            tile_buffer["cardinal_cells"] = [
                {
                    key: cell.get(key)
                    for key in ("relative", "value", "family", "occupied")
                }
                for cell in tile_buffer.get("cardinal_cells", [])
            ]
        feedback = raw.get("feedback", {})
        if isinstance(feedback, dict):
            feedback = {
                "score": feedback.get("score", 0),
                "recent": [
                    {key: entry.get(key) for key in ("kind", "delta", "feedback")}
                    for entry in feedback.get("recent", [])[-3:]
                ],
                "policy": feedback.get("policy"),
            }
        recent_actions = []
        for action in raw.get("recent_agent_actions", [])[-4:]:
            action_feedback = action.get("feedback", {})
            recent_actions.append({
                "kind": action.get("kind"),
                "from": action.get("before", {}).get("position"),
                "to": action.get("after", {}).get("position"),
                "facing_before": action.get("before", {}).get("direction"),
                "facing_after": action.get("after", {}).get("direction"),
                "requested_direction": action.get("requested_direction"),
                "requested_tiles": action.get("requested_tiles"),
                "tool": action.get("tool"),
                "feedback": action_feedback.get("feedback"),
                "reward": action_feedback.get("delta"),
            })
        context = {
            "goal": str(raw.get("goal", ""))[:500],
            "game": game,
            "strategic_progression": raw.get("strategic_progression", {}),
            "dungeon_context": dungeon,
            "navigation_map": navigation_map,
            "tile_buffer": tile_buffer,
            "tutorial": raw.get("tutorial", {}),
            "selected_dungeon_tool": raw.get("selected_dungeon_tool"),
            "available_actions": raw.get("available_actions", []),
            "recent_agent_actions": recent_actions,
            "feedback": feedback,
            "navigation": raw.get("navigation", {}),
            "episode_summary": self.summary,
            "recent_events": events,
            "reasoning_evidence": raw.get("reasoning_evidence", [])[-4:],
        }
        # Leave headroom for the context_budget field and small schema changes.
        target_chars = max(1000, self.max_chars - min(1000, self.max_chars // 5))
        encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > target_chars:
            context["recent_events"] = events[-3:]
            context["reasoning_evidence"] = context["reasoning_evidence"][-2:]
            compact_dungeon = context.get("dungeon_context")
            if isinstance(compact_dungeon, dict):
                compact_dungeon["nearby_markers"] = compact_dungeon.get("nearby_markers", [])[:6]
            compact_map = context.get("navigation_map")
            if isinstance(compact_map, dict):
                context["navigation_map"] = {
                    key: compact_map[key]
                    for key in ("available", "dungeon", "coordinate_bounds", "ascii_crop", "legend", "nearby_curated_markers", "policy")
                    if key in compact_map
                }
                context["navigation_map"]["nearby_curated_markers"] = context["navigation_map"].get("nearby_curated_markers", [])[:6]
            context["episode_summary"]["recent_outcomes"] = self.summary["recent_outcomes"][-5:]
            context["episode_summary"]["progression_items"] = []
            encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > target_chars:
            context["game"]["party"] = [
                {"name": member["name"], "status": member["status"], "hp": member["hp"]}
                for member in context["game"]["party"]
            ]
            encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > target_chars:
            context["recent_agent_actions"] = context["recent_agent_actions"][-2:]
            context["feedback"]["recent"] = context["feedback"].get("recent", [])[-3:]
            context["episode_summary"]["recent_outcomes"] = context["episode_summary"].get(
                "recent_outcomes", []
            )[-3:]
            encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > target_chars:
            navigation = context.get("navigation", {})
            if isinstance(navigation, dict):
                navigation = dict(navigation)
                progress = dict(navigation.get("progress", {}))
                progress.pop("objective", None)  # already supplied as goal
                progress["room_history"] = progress.get("room_history", [])[-4:]
                navigation["progress"] = progress
                room = dict(navigation.get("current_room", {}))
                room["nearby_live_landmarks"] = room.get("nearby_live_landmarks", [])[:3]
                navigation["current_room"] = room
                context["navigation"] = navigation
            episode = context.get("episode_summary", {})
            if isinstance(episode, dict):
                context["episode_summary"] = {
                    "maps_seen": episode.get("maps_seen", []),
                    "recent_outcomes": episode.get("recent_outcomes", [])[-3:],
                    "blocked_counts": episode.get("blocked_counts", {}),
                    "compactions": episode.get("compactions", 0),
                }
            encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > target_chars:
            tutorial = context.get("tutorial", {})
            if isinstance(tutorial, dict):
                tutorial = dict(tutorial)
                tutorial.pop("teaching_style", None)
                tutorial.pop("question_policy", None)
                context["tutorial"] = tutorial
            navigation = context.get("navigation", {})
            if isinstance(navigation, dict):
                room = dict(navigation.get("current_room", {}))
                room["nearby_live_landmarks"] = room.get("nearby_live_landmarks", [])[:2]
                navigation = dict(navigation)
                navigation["current_room"] = room
                context["navigation"] = navigation
            encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > self.max_chars:
            raise ValueError(
                f"Compacted model context is still {len(encoded)} chars; budget is {self.max_chars}"
            )
        self.summary_path.write_text(
            json.dumps(self.summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        context["context_budget"] = {
            "chars": len(encoded),
            "estimated_tokens": (len(encoded) + 3) // 4,
            "max_chars": self.max_chars,
        }
        return context


class ThinkingGate:
    """Reject looping or state-contradicting model decisions."""

    def __init__(self, config: dict):
        self.max_seconds = min(float(config.get("max_thinking_seconds", 270)), 295.0)
        self.max_same_intent = int(config.get("max_same_intent_without_change", 2))
        self._last_signature = None
        self._last_fingerprint = None
        self._repeat_count = 0

    @staticmethod
    def fingerprint(context: dict) -> tuple:
        game = context["game"]
        return (
            game.get("map_id"),
            tuple(game.get("position", [])),
            game.get("mode"),
            tuple(game.get("progression_items", [])),
            context.get("selected_dungeon_tool"),
            game.get("event_flags_digest"),
            game.get("dungeon_flags_digest"),
            context.get("navigation", {}).get("current_room", {}).get("id"),
            tuple(context.get("tile_buffer", {}).get("rows", [])),
        )

    def validate(self, intent: Intent, context: dict, elapsed_seconds: float) -> None:
        if elapsed_seconds > self.max_seconds:
            raise ModelDriftError(
                f"model exceeded thinking gate: {elapsed_seconds:.1f}s > {self.max_seconds:.1f}s"
            )
        gate_intent(intent, str(context["game"].get("mode", "other")))
        if intent.kind == "move" and intent.direction == context["game"].get("blocked_direction"):
            raise ModelDriftError("model tried the currently observed blocked direction")
        if intent.kind == "face" and intent.direction == context["game"].get("direction"):
            raise ModelDriftError("model tried to face the direction already active")
        if intent.kind == "select_tool" and intent.tool == context.get("selected_dungeon_tool"):
            raise ModelDriftError("model tried to re-select the already selected dungeon tool")

        room = context.get("navigation", {}).get("current_room", {})
        for landmark in room.get("nearby_live_landmarks", []):
            readiness = landmark.get("action_readiness", {})
            if readiness.get("completed"):
                continue
            if not readiness.get("position_ready"):
                continue
            if intent.kind == "move":
                raise ModelDriftError(
                    f"model tried to leave active action landmark {landmark.get('id')}; "
                    f"next precondition is {readiness.get('next_precondition') or landmark.get('action')}"
                )
            required_facing = readiness.get("required_facing")
            if intent.kind == "face" and required_facing and intent.direction != required_facing:
                raise ModelDriftError(
                    f"action landmark requires facing {required_facing}, not {intent.direction}"
                )
            break

        signature = json.dumps(asdict(intent), sort_keys=True)
        fingerprint = self.fingerprint(context)
        if signature == self._last_signature and fingerprint == self._last_fingerprint:
            self._repeat_count += 1
        else:
            self._repeat_count = 1
        self._last_signature = signature
        self._last_fingerprint = fingerprint
        if self._repeat_count > self.max_same_intent:
            raise ModelDriftError("model repeated the same intent without an observed state change")
