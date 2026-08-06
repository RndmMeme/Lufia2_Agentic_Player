"""Bounded context memory and drift gates for local model decisions."""

from __future__ import annotations

import json
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
        mode = str(game.get("mode", "other"))
        result = {
            "map_id": game.get("map_id"),
            "map_name": game.get("map_name"),
            "zone_id": game.get("zone_id"),
            "zone_name": game.get("zone_name"),
            "position": [game.get("x"), game.get("y")],
            "previous_direction": game.get("previous_direction"),
            "direction": game.get("direction"),
            "blocked_direction": game.get("blocked_direction"),
            "mode": mode,
        }
        if game.get("dialog_active"):
            result["dialog_active"] = True
        if mode == "battle":
            result["party"] = [
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
            result["enemies"] = [
                {
                    "slot": enemy.get("slot"),
                    "id": enemy.get("identity"),
                    "hp": enemy.get("hp"),
                    "status": enemy.get("status"),
                }
                for enemy in game.get("enemies", [])
            ]
        return result

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
        self.summary["progression_items"] = []

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
            compact_action = {
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
            }
            semantic_changes = action.get("map_tile_changes", [])
            if int(action.get("map_tile_change_count", 0)) > 0:
                completion = action.get("completed_landmark") or {}
                compact_action["confirmed_world_change"] = {
                    "semantic_tile_count": int(action.get("map_tile_change_count", 0)),
                    "changed_live_tiles": [
                        change.get("live") for change in semantic_changes if change.get("live")
                    ],
                    "completed_landmark": completion.get("landmark_id"),
                    "effect_reference": "navigation.confirmed_world_changes",
                    "visual_instruction": (
                        "Compare PREVIOUS and CURRENT: the action succeeded and changed the remote "
                        "world region shown here. Treat the changed result as the current traversability hypothesis."
                    ),
                }
            recent_actions.append(compact_action)
        spatial = raw.get("spatial_correlation")
        if isinstance(spatial, dict):
            # Keep the actionable correlation once. Drop bookkeeping booleans,
            # prose scope, and duplicate inference text that the system prompt
            # already supplies.
            spatial = {
                "attempted_direction": spatial.get("attempted_direction"),
                "adjacent_tile": spatial.get("adjacent_tile"),
                "curated_map_evidence": spatial.get("curated_map_evidence"),
                "map_proves_wall_or_block": spatial.get("map_proves_wall_or_block"),
                "conclusion": spatial.get("conclusion"),
                "target": spatial.get("target"),
                "target_components": spatial.get("target_components", []),
                "local_alternatives": spatial.get("local_alternatives", []),
                "blocked_edge_tests": spatial.get("blocked_edge_tests", []),
            }
        context = {
            "goal": str(raw.get("goal", ""))[:500],
            "game": game,
            "strategic_progression": raw.get("strategic_progression", {}),
            "dungeon_context": dungeon,
            "navigation_map": navigation_map,
            "tile_buffer": tile_buffer,
            "spatial_correlation": spatial,
            "tutorial": raw.get("tutorial", {}),
            "selected_dungeon_tool": raw.get("selected_dungeon_tool"),
            "exploration_relevant_items": raw.get("exploration_relevant_items", []),
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
            if "party" in context["game"]:
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
        if len(encoded) > target_chars:
            # Last-resort compaction keeps the decision-critical map, evidence,
            # and complete action vocabulary.  Removing those fields can itself
            # manufacture a navigation stall.
            context["reasoning_evidence"] = context.get("reasoning_evidence", [])[-2:]
            context["recent_events"] = context.get("recent_events", [])[-2:]
            context["recent_agent_actions"] = context.get("recent_agent_actions", [])[-1:]
            navigation_map = context.get("navigation_map", {})
            if isinstance(navigation_map, dict):
                navigation_map["nearby_curated_markers"] = navigation_map.get(
                    "nearby_curated_markers", []
                )[:3]
            navigation = context.get("navigation", {})
            if isinstance(navigation, dict):
                room = navigation.get("current_room", {})
                if isinstance(room, dict):
                    room["nearby_live_landmarks"] = room.get("nearby_live_landmarks", [])[:2]
                    room.pop("bounds", None)
                    room.pop("predecessors", None)
                    room.pop("successors", None)
                    room.pop("success_evidence", None)
                progress = navigation.get("progress", {})
                if isinstance(progress, dict):
                    progress["visited_rooms"] = progress.get("visited_rooms", [])[-3:]
                    progress["missing_rooms"] = progress.get("missing_rooms", [])[:3]
                    progress["room_history"] = progress.get("room_history", [])[-2:]
                    progress.pop("nodes", None)
                    progress.pop("directed_edges", None)
                    progress.pop("actions", None)
                navigation.pop("map_scoped_rules", None)
                navigation.pop("semantics_sources", None)
            tile_buffer = context.get("tile_buffer", {})
            if isinstance(tile_buffer, dict):
                # The actor-local 3x3 rows are tiny and decision-critical.
                # Trim verbose cell metadata, never the local sensor itself.
                tile_buffer["cardinal_cells"] = tile_buffer.get("cardinal_cells", [])[:4]
            dungeon = context.get("dungeon_context", {})
            if isinstance(dungeon, dict):
                dungeon.pop("nearby_markers", None)
            strategic = context.get("strategic_progression", {})
            if isinstance(strategic, dict):
                strategic.pop("blocked_nearest_requirements", None)
                strategic["accessible"] = strategic.get("accessible", [])[:3]
            episode = context.get("episode_summary", {})
            if isinstance(episode, dict):
                episode.pop("blocked_counts", None)
                episode["recent_outcomes"] = episode.get("recent_outcomes", [])[-2:]
            encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > self.max_chars:
            # Runtime history is persisted on disk. At the hard prompt limit,
            # prefer current spatial evidence and the executable vocabulary.
            feedback = context.get("feedback", {})
            if isinstance(feedback, dict):
                feedback["recent"] = feedback.get("recent", [])[-1:]
                feedback.pop("policy", None)
            episode = context.get("episode_summary", {})
            if isinstance(episode, dict):
                context["episode_summary"] = {
                    "maps_seen": episode.get("maps_seen", []),
                    "recent_outcomes": episode.get("recent_outcomes", [])[-1:],
                }
            strategic = context.get("strategic_progression", {})
            if isinstance(strategic, dict) and strategic.get("deferred"):
                context["strategic_progression"] = {"deferred": True}
            encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > self.max_chars:
            # The complete episode summary remains persisted in
            # context_summary.json and is the least current item here.
            context.pop("episode_summary", None)
            encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > self.max_chars:
            # These headers duplicate game/navigation_map during an active
            # room-scoped objective. Current local evidence stays untouched.
            context.pop("dungeon_context", None)
            if context.get("strategic_progression", {}).get("deferred"):
                context.pop("strategic_progression", None)
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
            tuple(
                (item.get("name"), item.get("available"), item.get("selected"))
                for item in context.get("exploration_relevant_items", [])
            ),
            context.get("selected_dungeon_tool"),
            context.get("navigation", {}).get("current_room", {}).get("id"),
            tuple(context.get("tile_buffer", {}).get("rows", [])),
        )

    def validate(self, intent: Intent, context: dict, elapsed_seconds: float) -> None:
        if elapsed_seconds > self.max_seconds:
            raise ModelDriftError(
                f"model exceeded thinking gate: {elapsed_seconds:.1f}s > {self.max_seconds:.1f}s"
            )
        gate_intent(intent, str(context["game"].get("mode", "other")))
        available_kinds = {
            str(action).split(" ", 1)[0].split("(", 1)[0]
            for action in context.get("available_actions", [])
        }
        if available_kinds and intent.kind not in available_kinds:
            raise ModelDriftError(
                f"model chose unavailable action {intent.kind}; available={sorted(available_kinds)}"
            )
        if intent.kind == "move" and intent.direction == context["game"].get("blocked_direction"):
            raise ModelDriftError("model tried the currently observed blocked direction")
        if intent.kind == "face" and intent.direction == context["game"].get("direction"):
            raise ModelDriftError("model tried to face the direction already active")
        if intent.kind == "select_tool" and intent.tool == context.get("selected_dungeon_tool"):
            raise ModelDriftError("model tried to re-select the already selected dungeon tool")
        if intent.kind == "use_tool" and context.get("selected_dungeon_tool") is None:
            raise ModelDriftError("use_tool is technically unavailable because no dungeon tool is selected")
        if intent.kind == "select_tool":
            tool_state = {
                item.get("name"): bool(item.get("available"))
                for item in context.get("exploration_relevant_items", [])
            }
            if intent.tool in tool_state and not tool_state[intent.tool]:
                raise ModelDriftError(
                    f"model tried to select unavailable dungeon tool {intent.tool}"
                )

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
