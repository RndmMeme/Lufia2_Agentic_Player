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

    def reset_room_episode(self) -> None:
        """Discard prompt-summary evidence that belongs to the pre-reset room state."""
        self.summary["recent_outcomes"] = []
        self.summary["blocked_counts"] = {}
        self.summary_path.write_text(
            json.dumps(self.summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

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
                "semantic_action", "sequence_index", "selection_reason", "active", "completed", "action_readiness", "traversal",
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

    @staticmethod
    def _live_puzzle_overlay(
        navigation_map: dict,
        actor_live: list,
        object_live: list,
        receiver_live: list,
        stance_live: list | None,
        anchor_semantics: str | None = None,
        barrier_live: list[list[int]] | None = None,
    ) -> dict | None:
        """Overlay transient puzzle anchors on a small copy of the curated ASCII map."""
        points = [actor_live, object_live, receiver_live]
        if stance_live:
            points.append(stance_live)
        barriers = [
            point for point in (barrier_live or [])
            if isinstance(point, list) and len(point) == 2
        ]
        points.extend(barriers)
        if not all(isinstance(point, list) and len(point) == 2 for point in points):
            return None
        bounds = navigation_map.get("coordinate_bounds", {})
        source = navigation_map.get("ascii_crop")
        if not source or not all(key in bounds for key in ("min_x", "max_x", "min_y", "max_y")):
            return None

        min_x, max_x = int(bounds["min_x"]), int(bounds["max_x"])
        min_y, max_y = int(bounds["min_y"]), int(bounds["max_y"])
        source_rows = {}
        for line in str(source).splitlines():
            prefix, separator, row_cells = line.partition(" ")
            if not separator:
                continue
            try:
                row_y = int(prefix)
            except ValueError:
                continue
            source_rows[row_y] = list(row_cells)
        if not source_rows:
            return None

        local_min_x = max(min_x, min(int(point[0]) for point in points) - 1)
        local_max_x = min(max_x, max(int(point[0]) for point in points) + 1)
        local_min_y = max(min_y, min(int(point[1]) for point in points) - 1)
        local_max_y = min(max_y, max(int(point[1]) for point in points) + 1)
        cells = {}
        for row_y in range(local_min_y, local_max_y + 1):
            row = source_rows.get(row_y, [])
            for column_x in range(local_min_x, local_max_x + 1):
                index = column_x - min_x
                cells[(column_x, row_y)] = row[index] if 0 <= index < len(row) else "?"

        actor = tuple(int(value) for value in actor_live)
        movable = tuple(int(value) for value in object_live)
        receiver = tuple(int(value) for value in receiver_live)
        stance = tuple(int(value) for value in stance_live) if stance_live else None
        for barrier in barriers:
            cells[tuple(int(value) for value in barrier)] = "#"
        cells[receiver] = "S"
        if stance is not None:
            cells[stance] = "T"
        cells[movable] = "*" if movable == receiver else "P"
        cells[actor] = "@"

        rows = [
            "      " + " ".join(
                f"{column_x:02d}" for column_x in range(local_min_x, local_max_x + 1)
            )
        ]
        for row_y in range(local_min_y, local_max_y + 1):
            rows.append(
                f"y{row_y:02d}   "
                + "  ".join(cells[(column_x, row_y)] for column_x in range(local_min_x, local_max_x + 1))
            )
        return {
            "scope": "ephemeral_current_decision",
            "rows": "\n".join(rows),
            "legend": "@ actor feet; P movable-object anchor; S receiver; T next required actor stance; # temporary puzzle wall; * object anchor occupies receiver",
            "coordinate_rule": "x increases east; y increases south",
            "entities": {
                "actor_live": list(actor),
                "object_live": list(movable),
                "receiver_live": list(receiver),
                "next_stance_live": list(stance) if stance is not None else None,
                "actor_at_next_stance": actor == stance if stance is not None else None,
                "object_on_receiver": movable == receiver,
            },
            "anchor_semantics": anchor_semantics,
            "lifetime": "discard after this model decision; regenerate from the next live state",
        }

    @classmethod
    def _exploration_context(cls, context: dict) -> dict:
        """Keep one authoritative copy of live exploration evidence."""
        navigation = context.get("navigation", {})
        room = navigation.get("current_room", {}) if isinstance(navigation, dict) else {}
        tracked_object = navigation.get("tracked_movable_object", {})
        # Once WRAM has tracked a moved object, the provisional object at its
        # initial coordinate is stale and only gives the model two competing
        # targets for the same puzzle.
        provisional_object = (
            {} if tracked_object.get("estimated_live")
            else navigation.get("provisional_object_target", {})
        )
        dungeon_memory = context.get("established_memory", {}).get("dungeon", [])
        object_intent = next(
            (
                item for item in dungeon_memory
                if isinstance(item, dict) and item.get("form") == "object_intent"
            ),
            {},
        )
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
            and not item.get("completed")
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
            "completed_traversal_segment": navigation.get("completed_traversal_segment"),
            "local_layout_resolution": navigation.get("local_layout_resolution"),
            "local_route_evidence": navigation.get("local_route_evidence"),
            "tracked_movable_object": tracked_object,
            "provisional_object_target": provisional_object,
            "visual_progress_hypothesis": navigation.get("visual_progress_hypothesis"),
        }
        if not compact_navigation["active_landmark"]:
            compact_navigation.pop("active_landmark")
        if not compact_navigation["confirmed_world_changes"]:
            compact_navigation.pop("confirmed_world_changes")
        if not compact_navigation["completed_traversal_segment"]:
            compact_navigation.pop("completed_traversal_segment")
        if not compact_navigation["local_layout_resolution"]:
            compact_navigation.pop("local_layout_resolution")
        if not compact_navigation["local_route_evidence"]:
            compact_navigation.pop("local_route_evidence")
        if not compact_navigation["tracked_movable_object"]:
            compact_navigation.pop("tracked_movable_object")
        if not compact_navigation["provisional_object_target"]:
            compact_navigation.pop("provisional_object_target")
        if not compact_navigation["visual_progress_hypothesis"]:
            compact_navigation.pop("visual_progress_hypothesis")
        if not compact_navigation["observed_edges"]:
            compact_navigation.pop("observed_edges")

        confirmed_changes = navigation.get("confirmed_world_changes", [])[-2:]
        completed_changes = [
            change for change in confirmed_changes
            if change.get("source_landmark") != "observed_world_change"
        ]
        observed_state_changes = [
            {
                "action": change.get("source_landmark"),
                "result": change.get("effect", {}).get("message"),
                "status": "puzzle state changed; objective completion not yet proven",
            }
            for change in confirmed_changes
            if change.get("source_landmark") == "observed_world_change"
        ]
        confirmed_landmarks = {
            change.get("source_landmark") for change in completed_changes
        }
        completed_segment = navigation.get("completed_traversal_segment")
        visual_progress = navigation.get("visual_progress_hypothesis", {})
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
        final_alignment = object_intent.get("final_alignment", {})
        at_final_alignment = bool(
            final_alignment
            and tracked_object.get("estimated_live")
            == final_alignment.get("when_object_live")
        )
        object_at_required = bool(
            object_intent.get("required_live")
            and tracked_object.get("estimated_live")
            == object_intent.get("required_live")
        )
        if at_final_alignment or object_at_required:
            # current_step now targets the actor's pushing position. Keeping
            # the object's approach delta alongside it gives the model two
            # different movement targets for the same decision.
            compact_navigation.pop("tracked_movable_object", None)
        actor_live = context.get("position_update", {}).get("current", [])
        alignment_actor_target = final_alignment.get("actor_target_live", [])
        alignment_actor_route = [
            point for point in final_alignment.get("actor_route_live", [])
            if isinstance(point, list) and len(point) == 2
        ]
        if not alignment_actor_route and len(alignment_actor_target) == 2:
            alignment_actor_route = [alignment_actor_target]
        actor_at_alignment_target = bool(
            len(actor_live) == 2
            and len(alignment_actor_target) == 2
            and actor_live == alignment_actor_target
        )
        alignment_current_target = alignment_actor_target
        if at_final_alignment and alignment_actor_route and not actor_at_alignment_target:
            if actor_live in alignment_actor_route:
                route_index = alignment_actor_route.index(actor_live)
                alignment_current_target = alignment_actor_route[
                    min(route_index + 1, len(alignment_actor_route) - 1)
                ]
            else:
                alignment_current_target = alignment_actor_route[0]
        alignment_delta = (
            [
                int(alignment_current_target[0]) - int(actor_live[0]),
                int(alignment_current_target[1]) - int(actor_live[1]),
            ]
            if len(actor_live) == 2 and len(alignment_current_target) == 2
            else None
        )
        alignment_move = None
        if alignment_delta:
            delta_x, delta_y = alignment_delta
            if delta_x == 0 and delta_y != 0:
                alignment_move = {
                    "direction": "south" if delta_y > 0 else "north",
                    "count": abs(delta_y),
                }
            elif delta_y == 0 and delta_x != 0:
                alignment_move = {
                    "direction": "east" if delta_x > 0 else "west",
                    "count": abs(delta_x),
                }
        movable_live = (
            tracked_object.get("estimated_live")
            or provisional_object.get("live")
            or object_intent.get("initial_live")
        )
        opening_push = object_intent.get("opening_push", {})
        opening_active = bool(
            movable_live
            and movable_live == opening_push.get("when_object_live")
        )
        alignment_entry = object_intent.get("alignment_entry", {})
        entry_active = bool(
            movable_live
            and movable_live == alignment_entry.get("when_object_live")
        )
        alignment_push_direction = object_intent.get("alignment_push_direction")
        active_push_direction = (
            opening_push.get("interact_direction")
            if opening_active else alignment_push_direction
        )
        active_object_target = (
            opening_push.get("result_object_live")
            if opening_active else (
                object_intent.get("alignment_waypoint_live")
                or object_intent.get("required_live")
            )
        )
        required_push_side = {
            "north": "south of the object",
            "south": "north of the object",
            "west": "east of the object",
            "east": "west of the object",
        }.get(active_push_direction)
        push_side_vectors = {
            "north": (0, 1),
            "south": (0, -1),
            "west": (1, 0),
            "east": (-1, 0),
        }
        entry_route = [
            point for point in alignment_entry.get("actor_route_live", [])
            if isinstance(point, list) and len(point) == 2
        ]
        entry_target = entry_route[-1] if entry_route else []
        entry_current_target = entry_target
        if entry_active and entry_route and actor_live != entry_target:
            if actor_live in entry_route:
                route_index = entry_route.index(actor_live)
                entry_current_target = entry_route[min(route_index + 1, len(entry_route) - 1)]
            else:
                entry_current_target = entry_route[0]
        stance_live = None
        if at_final_alignment:
            stance_live = alignment_current_target
        elif opening_active and len(opening_push.get("actor_target_live", [])) == 2:
            stance_live = opening_push["actor_target_live"]
        elif entry_active and len(entry_current_target) == 2:
            stance_live = entry_current_target
        elif movable_live and active_push_direction in push_side_vectors:
            stance_dx, stance_dy = push_side_vectors[active_push_direction]
            stance_live = [
                int(movable_live[0]) + stance_dx,
                int(movable_live[1]) + stance_dy,
            ]
        push_stance_delta = (
            [
                int(stance_live[0]) - int(actor_live[0]),
                int(stance_live[1]) - int(actor_live[1]),
            ]
            if (
                not at_final_alignment
                and len(actor_live) == 2
                and isinstance(stance_live, list)
                and len(stance_live) == 2
            )
            else None
        )
        push_stance_move = None
        if push_stance_delta:
            delta_x, delta_y = push_stance_delta
            if delta_x == 0 and delta_y != 0:
                push_stance_move = {
                    "direction": "south" if delta_y > 0 else "north",
                    "count": abs(delta_y),
                }
            elif delta_y == 0 and delta_x != 0:
                push_stance_move = {
                    "direction": "east" if delta_x > 0 else "west",
                    "count": abs(delta_x),
                }
        actor_at_push_stance = bool(push_stance_delta == [0, 0])
        push_checkpoint_action = ({
            "kind": "interact",
            "direction": active_push_direction,
        } if actor_at_push_stance and active_push_direction else None)
        opening_completed = bool(
            opening_push.get("result_object_live")
            and movable_live == opening_push.get("result_object_live")
        )
        opening_feedback = ({
            "status": "success",
            "message": (
                f"{opening_push.get('interact_direction', '').capitalize()} push succeeded once. "
                f"Another {opening_push.get('interact_direction')} push is not advised in this state. "
                + (
                    f"Move {push_stance_move['direction']} {push_stance_move['count']} tile(s) now."
                    if push_stance_move else
                    "Follow the next checkpoint now."
                )
            ),
            "completed_once": f"interact({opening_push.get('interact_direction')})",
            "object_after_live": movable_live,
            "not_advised": f"interact({opening_push.get('interact_direction')})",
            "reason": "the one-time opening push already reached its required object state",
            "next_actor_target_live": stance_live,
            **({"next_checkpoint_move": push_stance_move} if push_stance_move else {}),
            **({"next_checkpoint_action": push_checkpoint_action} if push_checkpoint_action else {}),
        } if opening_completed else None)
        solved_exit = object_intent.get("solved_exit", {})
        solved_exit_route = [
            point for point in solved_exit.get("actor_route_live", [])
            if isinstance(point, list) and len(point) == 2
        ]
        solved_exit_target = solved_exit_route[0] if solved_exit_route else None
        if object_at_required and solved_exit_route and actor_live in solved_exit_route:
            route_index = solved_exit_route.index(actor_live)
            if route_index + 1 < len(solved_exit_route):
                solved_exit_target = solved_exit_route[route_index + 1]
            else:
                delta = {
                    "north": (0, -1), "south": (0, 1),
                    "west": (-1, 0), "east": (1, 0),
                }.get(solved_exit.get("transition_direction"), (0, 0))
                solved_exit_target = [
                    int(actor_live[0]) + delta[0], int(actor_live[1]) + delta[1]
                ]
        solved_exit_move = None
        if object_at_required and solved_exit_target and len(actor_live) == 2:
            delta_x = int(solved_exit_target[0]) - int(actor_live[0])
            delta_y = int(solved_exit_target[1]) - int(actor_live[1])
            if delta_x == 0 and delta_y != 0:
                solved_exit_move = {
                    "direction": "south" if delta_y > 0 else "north",
                    "count": abs(delta_y),
                }
            elif delta_y == 0 and delta_x != 0:
                solved_exit_move = {
                    "direction": "east" if delta_x > 0 else "west",
                    "count": abs(delta_x),
                }
        task_progress = {
            "completed_steps": ([
                {
                    "landmark": change.get("source_landmark"),
                    "result": change.get("effect", {}).get("message"),
                }
                for change in completed_changes
            ] + ([{
                "landmark": completed_segment.get("id"),
                "result": completed_segment.get("success"),
            }] if completed_segment else []) + recent_checkpoint_completions),
            "current_step": ({
                "landmark": active.get("id"),
                "target": active.get("effective_live") or active.get("live"),
                "reason": active.get("selection_reason"),
                "traversal_phase": (active.get("traversal") or {}).get("phase"),
                "next_step": (active.get("traversal") or {}).get("next_step"),
                "checkpoint": active.get("checkpoint"),
            } if active else ({
                "objective": visual_progress.get("next_step"),
                "direction": visual_progress.get("exit_direction"),
                "success_evidence": visual_progress.get("success_evidence"),
                "status": visual_progress.get("status"),
            } if (
                not completed_segment and visual_progress.get("next_step")
            ) else ({
                "objective": "verify the solved puzzle state and use the opened exit",
                "object_current_live": tracked_object.get("estimated_live"),
                **({
                    "target": solved_exit_target,
                    "target_type": "opened_door_threshold",
                    "checkpoint_move": solved_exit_move,
                    "action_now": (
                        f"move({solved_exit_move['direction']}, count={solved_exit_move['count']})"
                    ),
                } if solved_exit_move else {
                    "action_now": "look or look_map, then navigate through the opened exit",
                }),
                "success_evidence": navigation.get("current_room", {}).get("success_evidence"),
                "status": "object target achieved; do not push it again",
            } if (
                not completed_segment
                and object_at_required
            ) else ({
                "objective": "finish aligning the tracked movable object",
                "target": alignment_current_target,
                "target_type": (
                    "actor_position_for_final_push"
                    if alignment_current_target == alignment_actor_target
                    else "actor_route_waypoint"
                ),
                "object_current_live": tracked_object.get("estimated_live"),
                "delta_from_actor": alignment_delta,
                **({"checkpoint_move": alignment_move} if alignment_move else {}),
                **({"checkpoint_action": {
                    "kind": "interact",
                    "direction": final_alignment.get("interact_direction"),
                }} if actor_at_alignment_target else {}),
                "action_now": (
                    f"interact({final_alignment.get('interact_direction')}) exactly once"
                    if actor_at_alignment_target else (
                        f"move({alignment_move['direction']}, count={alignment_move['count']})"
                        if alignment_move else "move toward the current target"
                    )
                ),
                "then": (
                    None if actor_at_alignment_target else (
                        f"at target, use interact({final_alignment.get('interact_direction')}) exactly once"
                        if alignment_current_target == alignment_actor_target else
                        "regenerate the live puzzle overlay for the next checkpoint"
                    )
                ),
                "success_evidence": navigation.get("current_room", {}).get("success_evidence"),
                "status": (
                    "actor is at target; perform the stated final push now"
                    if actor_at_alignment_target else
                    "reposition the actor with move; do not interact before reaching target"
                ),
            } if (
                not completed_segment
                and at_final_alignment
            ) else ({
                "objective": navigation.get("current_room", {}).get("objective"),
                "target": stance_live or tracked_object.get("estimated_live"),
                "target_type": "actor_position_for_push" if stance_live else "movable_object",
                "object_current_live": tracked_object.get("estimated_live"),
                **({"delta_from_actor": push_stance_delta} if push_stance_delta is not None else {}),
                **({"checkpoint_move": push_stance_move} if push_stance_move else {}),
                **({"checkpoint_action": push_checkpoint_action} if push_checkpoint_action else {}),
                **({
                    "required_object_live": (
                        active_object_target
                    ),
                    "useful_push_direction": active_push_direction,
                    "required_push_side": required_push_side,
                    "next_stance_live": stance_live,
                    "actor_forbidden_live": object_intent.get("actor_forbidden_live"),
                } if object_intent else {}),
                "action_readiness": tracked_object.get("action_readiness"),
                "intermediate_progress_evidence": (
                    "Actor reaches a cardinally adjacent tile, then a directed interact "
                    "visibly changes the movable object's position."
                ),
                "success_evidence": navigation.get("current_room", {}).get("success_evidence"),
                "status": (
                    "manipulate the tracked object until the room success evidence is proven; "
                    "actor adjacency or one successful push is intermediate only"
                ),
            } if (
                not completed_segment
                and tracked_object.get("estimated_live")
            ) else ({
                "objective": (
                    "reach the required push stance for the established movable object"
                    if object_intent else
                    "approach and contact-test the established provisional object candidate"
                ),
                "target": stance_live or movable_live,
                "target_type": "actor_position_for_push" if stance_live else provisional_object.get("identity"),
                "object_current_live": movable_live,
                **({"delta_from_actor": push_stance_delta} if push_stance_delta is not None else {}),
                **({"checkpoint_move": push_stance_move} if push_stance_move else {}),
                **({"checkpoint_action": push_checkpoint_action} if push_checkpoint_action else {}),
                "distance_reducing_directions": provisional_object.get(
                    "direct_distance_reducing_directions"
                ),
                "action_readiness": provisional_object.get("action_readiness"),
                "success_evidence": provisional_object.get("success_evidence"),
                "status": provisional_object.get("status"),
            } if (
                not completed_segment
                and (
                    provisional_object.get("live")
                    or (object_intent and movable_live)
                )
            ) else ({
                "objective": navigation.get("current_room", {}).get("objective"),
                "success_evidence": navigation.get("current_room", {}).get("success_evidence"),
                "status": "in_progress",
            } if (
                not completed_segment
                and navigation.get("current_room", {}).get("objective")
            ) else None))))))),
            "observed_state_changes": observed_state_changes,
            **({"immediate_phase_feedback": opening_feedback} if opening_feedback else {}),
            "instruction": (
                "Only completed_steps are finished. An observed_state_change is an attempt or intermediate "
                "puzzle state, not proof of completion. Continue current_step until its success_evidence is observed. "
                "For a movable-object puzzle, reaching the object or moving it once is not room completion. "
                "If a traversal segment just completed and current_step is null, choose the next local route freely."
            ),
        }

        navigation_map = context.get("navigation_map", {})
        compact_map = {
            key: navigation_map.get(key)
            for key in (
                "available", "dungeon", "coordinate_bounds", "ascii_crop",
                "legend", "full_map_image", "reason", "local_policy",
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
        puzzle_overlay = cls._live_puzzle_overlay(
            navigation_map,
            actor_live,
            movable_live or [],
            object_intent.get("required_live", []),
            None if object_at_required else stance_live,
            object_intent.get("anchor_semantics"),
            None if object_at_required else object_intent.get("ephemeral_barrier_live"),
        )
        if puzzle_overlay:
            compact_map["live_puzzle_overlay"] = puzzle_overlay

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
        established_memory = context.get("established_memory", {})
        if tracked_object.get("estimated_live") and object_intent:
            established_memory = dict(established_memory)
            established_memory["dungeon"] = [
                item for item in established_memory.get("dungeon", [])
                if item is not object_intent
            ]
        position_update = dict(context.get("position_update", {}))
        if at_final_alignment or object_at_required:
            position_update.pop("tracked_movable_object", None)
        result = {
            "goal": context.get("goal"),
            "game": context.get("game", {}),
            "position_update": position_update,
            "navigation_map": compact_map,
            "tile_buffer": compact_tiles,
            "visible_object_candidates": context.get("visible_object_candidates", {}),
            "tutorial": compact_tutorial,
            "established_memory": established_memory,
            "selected_dungeon_tool": context.get("selected_dungeon_tool"),
            "exploration_relevant_items": tools,
            "available_actions": context.get("available_actions", []),
            "recent_agent_actions": context.get("recent_agent_actions", [])[-1:],
            "navigation": compact_navigation,
            "task_progress": task_progress,
            "reasoning_evidence": context.get("reasoning_evidence", [])[-1:],
            "memory_access": context.get("memory_access", {}),
            "room_episode": context.get("room_episode", {}),
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
            "visible_object_candidates": raw.get("visible_object_candidates", {}),
            "spatial_correlation": spatial,
            "tutorial": raw.get("tutorial", {}),
            "established_memory": raw.get("established_memory", {}),
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
            "room_episode": raw.get("room_episode", {}),
        }
        if game.get("mode") == "exploration":
            context = self._exploration_context(context)
        # Leave headroom for the context_budget field and small schema changes.
        target_chars = max(1000, self.max_chars - min(1000, self.max_chars // 5))
        encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > target_chars:
            established = context.get("established_memory", {})
            if isinstance(established, dict):
                # Current dungeon facts outrank global mechanics, which are
                # also present in the stable system contract.
                established["global"] = []
            navigation = context.get("navigation", {})
            if isinstance(navigation, dict):
                # The full explored-edge graph persists in the mapper. The
                # current decision already has local_route_evidence, so replaying
                # the historical graph only consumes prompt budget.
                navigation.pop("observed_edges", None)
                recent_changed_landmarks = {
                    (action.get("confirmed_world_change") or {}).get("completed_landmark")
                    for action in context.get("recent_agent_actions", [])
                    if action.get("confirmed_world_change")
                }
                compact_changes = []
                for change in navigation.get("confirmed_world_changes", []):
                    if change.get("source_landmark") in recent_changed_landmarks:
                        compact_changes.append(change)
                        continue
                    effect = change.get("effect", {})
                    compact_changes.append({
                        "source_landmark": change.get("source_landmark"),
                        "source_live": change.get("source_live"),
                        "effect": {
                            key: effect.get(key)
                            for key in ("state", "message")
                            if effect.get(key) is not None
                        },
                        "changed_live_tiles": change.get("changed_live_tiles", [])[:6],
                        "authority": change.get("authority"),
                    })
                if compact_changes:
                    navigation["confirmed_world_changes"] = compact_changes
            context["recent_events"] = events[-3:]
            context["reasoning_evidence"] = context["reasoning_evidence"][-2:]
            compact_dungeon = context.get("dungeon_context")
            if isinstance(compact_dungeon, dict):
                compact_dungeon["nearby_markers"] = compact_dungeon.get("nearby_markers", [])[:6]
            compact_map = context.get("navigation_map")
            if isinstance(compact_map, dict):
                context["navigation_map"] = {
                    key: compact_map[key]
                    for key in (
                        "available", "dungeon", "coordinate_bounds", "ascii_crop",
                        "legend", "nearby_curated_markers", "live_puzzle_overlay", "policy",
                    )
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
            largest = sorted(
                (
                    (key, len(json.dumps(value, ensure_ascii=False, separators=(",", ":"))))
                    for key, value in context.items()
                ),
                key=lambda item: item[1],
                reverse=True,
            )[:8]
            navigation_sizes = sorted(
                (
                    (key, len(json.dumps(value, ensure_ascii=False, separators=(",", ":"))))
                    for key, value in context.get("navigation", {}).items()
                ),
                key=lambda item: item[1],
                reverse=True,
            )
            raise ValueError(
                f"Compacted model context is still {len(encoded)} chars; budget is {self.max_chars}; "
                f"largest_fields={largest}; navigation_fields={navigation_sizes}"
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

    def reset_room_episode(self) -> None:
        """Forget intent-loop history from the puzzle state that was reset."""
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
        recent_actions = context.get("recent_agent_actions", [])
        if intent.kind == "interact" and intent.direction and recent_actions:
            previous = recent_actions[-1]
            if (
                previous.get("kind") == "interact"
                and previous.get("requested_direction") == intent.direction
                and previous.get("from") == context["game"].get("position")
                and previous.get("to") == context["game"].get("position")
                and not previous.get("confirmed_world_change")
            ):
                raise ModelDriftError(
                    "the same directed interact already had no effect at this exact tile; "
                    "change position, direction, or inspect the scene"
                )
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

        signature = json.dumps({
            "kind": intent.kind,
            "direction": intent.direction,
            "count": intent.count,
            "question": intent.question,
            "query": intent.query,
            "tool": intent.tool,
        }, sort_keys=True)
        fingerprint = self.fingerprint(context)
        if signature == self._last_signature and fingerprint == self._last_fingerprint:
            self._repeat_count += 1
        else:
            self._repeat_count = 1
        self._last_signature = signature
        self._last_fingerprint = fingerprint
        if self._repeat_count > self.max_same_intent:
            raise ModelDriftError("model repeated the same intent without an observed state change")
