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
        self.stats_path = run_dir / "prompt_stats.jsonl"
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
            "index", "type", "outcome", "direction", "from", "to", "new_room", "room",
            "map_id", "x", "y",
        )
        return {key: event[key] for key in allowed if key in event}

    @staticmethod
    def _landmark(landmark: dict) -> dict:
        result = {
            key: landmark.get(key)
            for key in (
                "id", "live", "effective_live", "relative", "kind", "action", "tool", "facing",
                "selection_reason", "active", "completed", "action_readiness", "traversal",
                "checkpoint",
            )
            if landmark.get(key) is not None
        }
        relation = landmark.get("derived_relation", {})
        if relation:
            result["relation"] = {
                key: relation.get(key)
                for key in ("at_landmark", "manhattan_tiles", "steps_to_reach")
                if relation.get(key) is not None
            }
        return result

    @classmethod
    def _exploration_context(cls, context: dict) -> dict:
        """Keep one authoritative copy of live exploration evidence."""
        navigation = context.get("navigation", {})
        room = navigation.get("current_room", {}) if isinstance(navigation, dict) else {}
        active = cls._landmark(navigation.get("active_landmark", {}))
        active_id = active.get("id")
        references = [
            {
                key: item.get(key)
                for key in ("id", "live", "kind", "action", "tool", "facing")
                if item.get(key) is not None
            }
            for item in room.get("nearby_live_landmarks", [])
            if item.get("id") != active_id
        ][:3]
        compact_room = {
            "id": room.get("id"),
            "objective": room.get("objective"),
            "success_evidence": room.get("success_evidence"),
            "reference_landmarks": references,
        }
        compact_navigation = {
            "current_room": compact_room,
            "active_landmark": active,
            "observed_edges": navigation.get("observed_edges", {}),
            "confirmed_world_changes": navigation.get("confirmed_world_changes", [])[-2:],
        }
        if not compact_navigation["active_landmark"]:
            compact_navigation.pop("active_landmark")
        if not compact_navigation["confirmed_world_changes"]:
            compact_navigation.pop("confirmed_world_changes")
        if not compact_navigation["observed_edges"]:
            compact_navigation.pop("observed_edges")

        confirmed_changes = navigation.get("confirmed_world_changes", [])[-2:]
        confirmed_landmarks = {
            change.get("source_landmark") for change in confirmed_changes
        }
        recent_checkpoint_completions = []
        for action in context.get("recent_agent_actions", [])[-4:]:
            checkpoint = action.get("completed_checkpoint")
            if (
                checkpoint
                and checkpoint.get("id") not in confirmed_landmarks
                and not any(
                item.get("landmark") == checkpoint.get("id")
                for item in recent_checkpoint_completions
                )
            ):
                recent_checkpoint_completions.append({
                    "landmark": checkpoint.get("id"),
                    "result": checkpoint.get("success"),
                })
        task_progress = {
            "completed_steps": ([
                {
                    "landmark": change.get("source_landmark"),
                    "result": change.get("effect", {}).get("message"),
                }
                for change in confirmed_changes
            ] + recent_checkpoint_completions),
            "current_step": {
                "landmark": active.get("id"),
                "target": active.get("effective_live") or active.get("live"),
                "reason": active.get("selection_reason"),
                "traversal_phase": (active.get("traversal") or {}).get("phase"),
                "next_step": (active.get("traversal") or {}).get("next_step"),
                "checkpoint": active.get("checkpoint"),
            } if active else None,
            "instruction": (
                "Completed goal clauses are finished. Act on current_step; do not restart the goal text."
            ),
        }

        navigation_map = context.get("navigation_map", {})
        compact_map = {
            key: navigation_map.get(key)
            for key in (
                "available", "dungeon", "coordinate_bounds", "ascii_crop",
                "legend", "full_map_image",
            )
            if navigation_map.get(key) is not None
        }
        compact_map["nearby_curated_markers"] = [
            {
                key: marker.get(key)
                for key in ("type", "relative", "traversal", "required_action", "notes")
                if marker.get(key) is not None
            }
            for marker in navigation_map.get("nearby_curated_markers", [])[:4]
        ]

        tutorial = context.get("tutorial", {})
        compact_tutorial = {
            "current_lessons": [
                {
                    key: lesson.get(key)
                    for key in ("id", "known_mechanic", "lesson")
                    if lesson.get(key) is not None
                }
                for lesson in tutorial.get("current_lessons", [])[:2]
            ]
        } if tutorial.get("active") else {"active": False}

        tile_buffer = context.get("tile_buffer", {})
        compact_tiles = {
            key: tile_buffer.get(key)
            for key in ("available", "role", "center_live", "rows")
            if tile_buffer.get(key) is not None
        }
        compact_tiles["cardinal_cells"] = [
            {
                key: cell.get(key)
                for key in ("relative", "family", "occupied")
                if cell.get(key) is not None
            }
            for cell in tile_buffer.get("cardinal_cells", [])[:4]
        ]

        tools = [
            {
                key: item.get(key)
                for key in ("name", "available", "selected", "locally_required")
            }
            for item in context.get("exploration_relevant_items", [])
        ]
        result = {
            "goal": context.get("goal"),
            "game": context.get("game", {}),
            "position_update": context.get("position_update", {}),
            "navigation_map": compact_map,
            "tile_buffer": compact_tiles,
            "tutorial": compact_tutorial,
            "selected_dungeon_tool": context.get("selected_dungeon_tool"),
            "exploration_relevant_items": tools,
            "available_actions": context.get("available_actions", []),
            "recent_agent_actions": context.get("recent_agent_actions", [])[-1:],
            "navigation": compact_navigation,
            "task_progress": task_progress,
            "reasoning_evidence": context.get("reasoning_evidence", [])[-1:],
            "memory_access": context.get("memory_access", {}),
        }
        for key in ("spatial_correlation", "strategic_progression"):
            value = context.get(key)
            if value and not (key == "strategic_progression" and value.get("deferred")):
                result[key] = value
        recovery = context.get("room_reset_recovery", {})
        if recovery.get("eligible"):
            result["room_reset_recovery"] = recovery
        return result

    def compact(self, raw: dict) -> dict:
        game = self._game(raw["game"])
        map_id = game.get("map_id")
        if map_id is not None and map_id not in self.summary["maps_seen"]:
            self.summary["maps_seen"].append(map_id)
        self.summary["progression_items"] = []

        events = [self._event(event) for event in raw.get("recent_events", [])[-6:]]
        seen_events = self.summary.setdefault("seen_event_indices", [])
        for event in events:
            event_index = event.get("index")
            if event_index is not None and event_index in seen_events:
                continue
            if event_index is not None:
                seen_events.append(event_index)
            if event.get("outcome"):
                self.summary["recent_outcomes"].append(event)
            if event.get("outcome") == "blocked_now":
                key = f"{event.get('from')}:{event.get('direction')}"
                self.summary["blocked_counts"][key] = self.summary["blocked_counts"].get(key, 0) + 1
        self.summary["recent_outcomes"] = self.summary["recent_outcomes"][-12:]
        self.summary["seen_event_indices"] = seen_events[-100:]
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
            if action.get("completed_checkpoint"):
                compact_action["completed_checkpoint"] = action.get("completed_checkpoint")
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
            "position_update": raw.get("position_update", {}),
            "strategic_progression": raw.get("strategic_progression", {}),
            "dungeon_context": dungeon,
            "navigation_map": navigation_map,
            "tile_buffer": tile_buffer,
            "spatial_correlation": spatial,
            "tutorial": raw.get("tutorial", {}),
            "selected_dungeon_tool": raw.get("selected_dungeon_tool"),
            "exploration_relevant_items": raw.get("exploration_relevant_items", []),
            "available_actions": raw.get("available_actions", []),
            "room_reset_recovery": raw.get("room_reset_recovery", {}),
            "recent_agent_actions": recent_actions,
            "feedback": feedback,
            "navigation": raw.get("navigation", {}),
            "episode_summary": self.summary,
            "recent_events": events,
            "reasoning_evidence": raw.get("reasoning_evidence", [])[-4:],
            "memory_access": raw.get("memory_access", {}),
        }
        if game.get("mode") == "exploration":
            context = self._exploration_context(context)
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
            episode = context.get("episode_summary")
            if isinstance(episode, dict):
                episode["recent_outcomes"] = self.summary["recent_outcomes"][-5:]
                episode["progression_items"] = []
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
            feedback = context.get("feedback")
            if isinstance(feedback, dict):
                feedback["recent"] = feedback.get("recent", [])[-3:]
            episode = context.get("episode_summary")
            if isinstance(episode, dict):
                episode["recent_outcomes"] = episode.get("recent_outcomes", [])[-3:]
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
        field_chars = {
            key: len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            for key, value in context.items()
            if key != "context_budget"
        }
        with self.stats_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "chars": len(encoded),
                "estimated_tokens": (len(encoded) + 3) // 4,
                "largest_fields": dict(sorted(
                    field_chars.items(), key=lambda item: item[1], reverse=True
                )[:8]),
            }, ensure_ascii=False, separators=(",", ":")) + "\n")
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
        if intent.kind == "reset_room" and not context.get("room_reset_recovery", {}).get("eligible"):
            raise ModelDriftError("room reset has no current curated recovery ticket")
        if intent.kind == "select_tool":
            tool_state = {
                item.get("name"): bool(item.get("available"))
                for item in context.get("exploration_relevant_items", [])
            }
            if intent.tool in tool_state and not tool_state[intent.tool]:
                raise ModelDriftError(
                    f"model tried to select unavailable dungeon tool {intent.tool}"
                )

        navigation = context.get("navigation", {})
        active = navigation.get("active_landmark", {})
        active_readiness = active.get("action_readiness", {})
        if (
            active.get("action") == "use_tool"
            and intent.kind == "use_tool"
            and not active_readiness.get("completed")
        ):
            if not active_readiness.get("position_ready"):
                raise ModelDriftError(
                    f"use_tool requires reaching active landmark {active.get('id')} first"
                )
            if not active_readiness.get("facing_ready"):
                raise ModelDriftError(
                    f"use_tool requires facing {active_readiness.get('required_facing')} first"
                )
        rationale = intent.rationale.casefold()
        if (
            active.get("action") == "use_tool"
            and intent.kind == "interact"
            and any(word in rationale for word in ("shoot", "fire", "arrow", "use tool"))
        ):
            raise ModelDriftError(
                "rationale describes dungeon-tool use, but interact presses A; choose use_tool at the ready landmark"
            )

        room = navigation.get("current_room", {})
        active_landmark = navigation.get("active_landmark")
        candidate_landmarks = (
            [active_landmark] if isinstance(active_landmark, dict) and active_landmark else []
        ) + list(room.get("nearby_live_landmarks", []))
        for landmark in candidate_landmarks:
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
