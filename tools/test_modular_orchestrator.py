"""Focused regression tests for the modular orchestrator integration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent.battle_runner import BattleRunner
from agent.context_builder import ContextBuilder, DUNGEON_TOOLS
from agent.context_harness import ModelDriftError, ThinkingGate
from agent.feedback_manager import FeedbackManager
from agent.dungeons.secret_skills_cave import SecretSkillsCave
from agent.established_memory import global_memory_context
from agent.intent import Intent
from agent.model_client import INTENT_FORMAT, VISION_FORMAT, LocalModelClient
from agent.model_gateway import ModelGateway
from agent.orchestrator import MesenOrchestrator
from agent.watchdog import ModelStallError
from run_agent import run_directory_lock, validate_run_directory


class _Response:
    status_code = 200
    text = ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "{}"}}]}


class _Journal:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def write(self, event: str, **details) -> None:
        self.events.append((event, details))


class _Watchdog:
    def run(self, choose, bark):
        bark(31.0)
        return choose(), 1.25


class _Gate:
    @staticmethod
    def fingerprint(context):
        return (context.get("goal"),)

    @staticmethod
    def validate(intent, context, elapsed):
        return None


class _Model:
    @staticmethod
    def choose_intent(context, max_move_batch):
        return Intent("wait", rationale="bounded test")


class _StalledBattle:
    def __init__(self) -> None:
        self.driver = SimpleNamespace(
            last_input_count=0,
            session=SimpleNamespace(stage=SimpleNamespace(value="action_cross")),
        )

    @staticmethod
    def step(observation):
        raise ModelStallError("bounded timeout")


class ModularOrchestratorTests(unittest.TestCase):
    def test_global_push_memory_requires_real_object_displacement(self) -> None:
        memories = global_memory_context("exploration", movable_object=True)
        push = next(item for item in memories if item["id"] == "push_requires_world_change")
        self.assertIn("object/map-state displacement", push["then"])

    def test_feedback_manager_marks_move_tile_diffs_as_scroll_observations(self) -> None:
        captured = {}

        class _Feedback:
            def record(self, kind, before, after, **details):
                captured.update(details)
                return {"delta": 0, "feedback": "neutral"}

        tile_buffers = SimpleNamespace(
            diff=lambda *args, **kwargs: {
                "semantic_count": 2, "count": 2, "changes": [{"live": [1, 1]}],
            },
            effect_context=lambda *args, **kwargs: {"available": False},
        )
        recorder = SimpleNamespace(record=lambda *args, **kwargs: None)
        manager = FeedbackManager(
            _Feedback(), recorder, None, tile_buffers, Path("."), memory=None
        )

        def observed(x):
            return SimpleNamespace(
                game=SimpleNamespace(
                    map_id=5, x=x, y=20, direction="east", mode="exploration",
                    blocked_direction=None, event_flags="00", dungeon_flags="00",
                ),
                wram=bytes(0x10000),
            )

        manager.remember_action("move", observed(4), observed(5))
        action = manager.recent_agent_actions[-1]
        self.assertEqual(0, action["map_tile_change_count"])
        self.assertEqual(2, action["map_tile_semantic_observation_count"])
        self.assertIn("scroll observations", action["map_tile_change_credit_policy"])
        self.assertEqual(0, captured["map_tile_change_count"])

    def test_delta_is_translated_to_distance_reducing_directions(self) -> None:
        self.assertEqual(
            ["east", "south"],
            MesenOrchestrator._directions_reducing_delta([5, 1]),
        )
        self.assertEqual(
            ["west", "north"],
            MesenOrchestrator._directions_reducing_delta([-2, -2]),
        )
        self.assertEqual(
            "south", MesenOrchestrator._direction_for_adjacent_delta([0, 1])
        )
        self.assertIsNone(MesenOrchestrator._direction_for_adjacent_delta([2, 0]))

    def test_only_repeated_no_effect_interacts_at_object_count_as_blocked_push(self) -> None:
        walking = [{
            "kind": "move", "direction": "east",
            "from": [10, 19], "to": [10, 19], "semantic_tile_changes": 0,
        }] * 3
        self.assertIsNone(
            MesenOrchestrator._blocked_push_evidence([11, 19], "east", walking)
        )
        pushes = [{
            "kind": "interact", "direction": "east",
            "from": [10, 19], "to": [10, 19], "semantic_tile_changes": 0,
        }] * 2
        evidence = MesenOrchestrator._blocked_push_evidence([11, 19], "east", pushes)
        self.assertEqual(2, evidence["consecutive_no_effect_pushes"])
        self.assertEqual([11, 19], evidence["object_live"])

    def test_successful_push_requires_one_current_visual_assessment(self) -> None:
        memory = {
            "recent_actions": [{
                "kind": "interact", "from": [7, 19], "to": [8, 19],
                "semantic_tile_changes": 3,
            }],
            "recent_perceptions": [],
        }
        self.assertTrue(MesenOrchestrator._post_push_assessment_required(memory, 12))
        memory["recent_perceptions"].append({"kind": "look", "action_count": 12})
        self.assertFalse(MesenOrchestrator._post_push_assessment_required(memory, 12))

    def test_strong_pillar_wall_vision_is_persistent_recovery_evidence(self) -> None:
        memory = {"recent_perceptions": [{
            "kind": "look",
            "result": {
                "relevant_objects": ["pillar", "wall"],
                "navigation_hypothesis": "The pillar is blocked by a wall and cannot move east.",
            },
        }]}
        confirmation = MesenOrchestrator._wall_confirmation(memory)
        self.assertTrue(confirmation["confirmed"])

        memory["recent_perceptions"][0]["result"]["navigation_hypothesis"] = (
            "A wall or temporary obstruction may be nearby."
        )
        self.assertIsNone(MesenOrchestrator._wall_confirmation(memory))

    def test_corroborated_switch_and_door_vision_requests_reversible_exit_test(self) -> None:
        positive = {
            "result": {
                "navigation_hypothesis": (
                    "The pillar is on the floor switch and the north door is passable."
                )
            }
        }
        memory = {"recent_perceptions": [positive, positive, {
            "result": {"navigation_hypothesis": "The door is blocked."}
        }]}
        hypothesis = MesenOrchestrator._visual_exit_hypothesis(memory)
        self.assertEqual("north", hypothesis["exit_direction"])
        self.assertEqual(2, hypothesis["positive_observations"])
        self.assertEqual(1, hypothesis["conflicting_observations"])
        self.assertEqual("WRAM-confirmed room transition", hypothesis["success_evidence"])

    def test_movable_object_approach_is_not_scored_as_puzzle_progress(self) -> None:
        context = {"navigation": {"tracked_movable_object": {"estimated_live": [8, 19]}}}
        self.assertIsNone(MesenOrchestrator._movement_feedback_target(context))

        active = {"id": "door", "live": [4, 5]}
        context["navigation"]["active_landmark"] = active
        self.assertIs(active, MesenOrchestrator._movement_feedback_target(context))

        context = {"navigation": {"provisional_object_target": {
            "id": "pillar_candidate", "live": [8, 21],
        }}}
        self.assertIsNone(MesenOrchestrator._movement_feedback_target(context))

        context = {
            "navigation": {},
            "task_progress": {"current_step": {
                "target_type": "actor_position_for_final_push",
                "target": [4, 22],
            }},
        }
        self.assertEqual(
            [4, 22],
            MesenOrchestrator._movement_feedback_target(context)["live"],
        )

    def test_wrong_selected_tool_can_be_replaced(self) -> None:
        builder = ContextBuilder.__new__(ContextBuilder)
        actions = builder._available_actions(None, None, "arrow")
        self.assertIn("select_tool(tool)", actions)
        self.assertIn("use_tool using Y", actions)

    def test_room_reset_is_advertised_only_with_recovery_ticket(self) -> None:
        builder = ContextBuilder.__new__(ContextBuilder)
        actions = builder._available_actions(None, None, "arrow")
        self.assertNotIn("reset_room", actions)
        eligible_actions = builder._available_actions(
            None, None, "arrow", room_reset_recovery={"eligible": True}
        )
        self.assertIn("reset_room (conditional puzzle recovery)", eligible_actions)
        self.assertIn(
            "reset_room",
            INTENT_FORMAT["properties"]["kind"]["enum"],
        )

    def test_room_reset_recovery_requires_mutation_and_two_failed_probes(self) -> None:
        navigation = {"current_room": {"reset_policy": {
            "enabled": True,
            "mutation_actions": ["interact"],
            "minimum_failed_actions_after_mutation": 2,
        }}}
        actions = [{
            "kind": "interact",
            "before": {"position": [8, 21]},
            "after": {"position": [7, 21]},
            "map_tile_change_count": 1,
            "navigation_relevant_change": True,
        }]
        self.assertFalse(ContextBuilder._room_reset_recovery(navigation, actions)["eligible"])
        for direction in ("north", "west"):
            actions.append({
                "kind": "interact",
                "before": {"position": [7, 21]},
                "after": {"position": [7, 21]},
                "requested_direction": direction,
                "map_tile_change_count": 0,
                "navigation_relevant_change": False,
            })
        recovery = ContextBuilder._room_reset_recovery(navigation, actions)
        self.assertTrue(recovery["eligible"])
        self.assertEqual(2, recovery["failed_probe_count"])

    def test_room_reset_recovery_does_not_treat_blocked_walking_as_correction(self) -> None:
        navigation = {"current_room": {"reset_policy": {
            "enabled": True,
            "mutation_actions": ["interact"],
            "minimum_failed_actions_after_mutation": 2,
        }}}
        actions = [{"kind": "interact", "map_tile_change_count": 1}]
        for direction in ("north", "west", "south"):
            actions.append({
                "kind": "move",
                "before": {"position": [7, 21]},
                "after": {"position": [7, 21]},
                "requested_direction": direction,
                "map_tile_change_count": 0,
                "navigation_relevant_change": False,
            })
        recovery = ContextBuilder._room_reset_recovery(navigation, actions)
        self.assertFalse(recovery["eligible"])
        self.assertEqual(0, recovery["failed_probe_count"])

    def test_room_reset_recovery_requires_new_mutation_after_reset(self) -> None:
        navigation = {"current_room": {"reset_policy": {"enabled": True}}}
        actions = [
            {"kind": "interact", "map_tile_change_count": 1},
            {"kind": "reset_room", "map_tile_change_count": 0},
            {"kind": "move", "before": {"position": [7, 21]}, "after": {"position": [7, 21]}},
            {"kind": "move", "before": {"position": [7, 21]}, "after": {"position": [7, 21]}},
        ]
        self.assertFalse(ContextBuilder._room_reset_recovery(navigation, actions)["eligible"])

    def test_position_update_reports_actual_delta_and_remaining_target(self) -> None:
        update = ContextBuilder._position_update(
            [17, 23],
            [{
                "kind": "move",
                "before": {"position": [21, 26]},
                "after": {"position": [17, 23]},
                "requested_direction": "west",
                "requested_tiles": 4,
            }],
            {"id": "west_door_approach", "live": [17, 23]},
        )
        self.assertEqual([-4, -3], update["last_move"]["actual_delta"])
        self.assertEqual([0, 0], update["active_target"]["delta_from_current"])

    def test_position_update_uses_forward_transit_target_not_anchor(self) -> None:
        update = ContextBuilder._position_update(
            [17, 22],
            [],
            {
                "id": "west_door_approach",
                "live": [17, 23],
                "effective_live": [17, 21],
                "traversal": {"phase": "crossing_threshold"},
            },
        )
        self.assertEqual([17, 21], update["active_target"]["position"])
        self.assertEqual([0, -1], update["active_target"]["delta_from_current"])
        self.assertEqual("next_threshold_step", update["active_target"]["role"])

    def test_perception_is_once_per_unchanged_state(self) -> None:
        builder = ContextBuilder.__new__(ContextBuilder)
        first = builder._available_actions(None, None, "arrow", [])
        after_look = builder._available_actions(None, None, "arrow", [{"type": "look"}])
        after_both = builder._available_actions(
            None, None, "arrow", [{"type": "look"}, {"type": "look_map"}]
        )
        self.assertIn("look at current frame", first)
        self.assertNotIn("look at current frame", after_look)
        self.assertIn("look_map at current frame plus full curated dungeon map", after_look)
        self.assertNotIn("look at current frame", after_both)
        self.assertNotIn("look_map at current frame plus full curated dungeon map", after_both)

    def test_completed_transit_masks_stale_previous_room_context(self) -> None:
        navigation = {
            "completed_traversal_segment": {
                "id": "north_door",
                "status": "segment_boundary_reached",
            },
            "active_landmark": {"id": "north_door", "live": [17, 23]},
            "current_room": {
                "id": "room_3",
                "objective": "Old room objective",
                "nearby_live_landmarks": [{"id": "old_switch"}],
            },
        }
        navigation_map, unresolved = ContextBuilder._suppress_unresolved_transit_context(
            navigation,
            {"available": True, "ascii_crop": "stale map"},
        )
        self.assertTrue(unresolved)
        self.assertFalse(navigation_map["available"])
        self.assertNotIn("ascii_crop", navigation_map)
        self.assertNotIn("active_landmark", navigation)
        self.assertIsNone(navigation["current_room"]["id"])
        self.assertFalse(navigation["current_room"]["resolved"])
        self.assertEqual(
            "unresolved_after_transit",
            navigation["local_layout_resolution"]["status"],
        )

    def test_normal_room_keeps_curated_map_context(self) -> None:
        navigation = {"current_room": {"id": "room_3"}}
        navigation_map = {"available": True, "ascii_crop": "current map"}
        result, unresolved = ContextBuilder._suppress_unresolved_transit_context(
            navigation, navigation_map
        )
        self.assertFalse(unresolved)
        self.assertIs(result, navigation_map)
        self.assertEqual("room_3", navigation["current_room"]["id"])

    def test_local_route_evidence_separates_tested_and_untried_edges(self) -> None:
        evidence = ContextBuilder._local_route_evidence({
            "observed_edges": {
                "east": {"outcome": "open", "to": "05:room_3:18,23"},
                "west": {"outcome": "blocked_now", "to": None},
            },
            "unknown_directions": ["south"],
        })
        self.assertEqual("east", evidence["passable"][0]["direction"])
        self.assertEqual("west", evidence["impassable_now"][0]["direction"])
        self.assertEqual(["south"], evidence["untried"])

    def test_local_route_evidence_marks_only_immediate_loop_reverse(self) -> None:
        evidence = ContextBuilder._local_route_evidence(
            {
                "observed_edges": {
                    "north": {"outcome": "open", "to": "north_node"},
                    "east": {"outcome": "open", "to": "east_node"},
                },
                "unknown_directions": [],
            },
            [{
                "kind": "move",
                "requested_direction": "south",
                "before": {"position": [17, 22]},
                "after": {"position": [17, 23]},
                "feedback": {"local_edge_traversal_count": 5},
            }],
        )
        self.assertEqual(
            "north", evidence["recent_non_progressing_edge"]["reverse_from_current"]
        )
        by_direction = {item["direction"]: item for item in evidence["passable"]}
        self.assertTrue(by_direction["north"]["recent_non_progressing"])
        self.assertFalse(by_direction["east"]["recent_non_progressing"])

    def test_fully_ready_landmark_advertises_only_required_action(self) -> None:
        actions = [
            "move(direction,count=1..4)",
            "face(direction) using R+direction without moving",
            "use_tool using Y",
            "look at current frame",
        ]
        navigation = {"current_room": {"nearby_live_landmarks": [{
            "id": "arrow_firing_position",
            "active": True,
            "action": "use_tool",
            "tool": "arrow",
            "action_readiness": {
                "completed": False,
                "position_ready": True,
                "facing_ready": True,
                "next_precondition": None,
            },
        }]}}
        self.assertEqual(
            ["use_tool using Y"],
            ContextBuilder._restrict_fully_ready_landmark_action(
                actions, navigation, selected_tool="arrow"
            ),
        )

    def test_landmark_does_not_restrict_actions_while_en_route(self) -> None:
        actions = [
            "move(direction,count=1..4)",
            "interact(direction optional) using A or direction+A",
            "use_tool using Y",
        ]
        navigation = {"active_landmark": {
            "id": "arrow_firing_position",
            "action": "use_tool",
            "tool": "arrow",
            "action_readiness": {
                "completed": False,
                "position_ready": False,
                "facing_ready": False,
                "next_precondition": "reach the landmark first",
            },
        }}
        self.assertEqual(
            actions,
            ContextBuilder._restrict_fully_ready_landmark_action(
                actions, navigation, selected_tool="arrow"
            ),
        )

    def test_landmark_at_position_advertises_missing_precondition(self) -> None:
        actions = [
            "move(direction,count=1..4)",
            "face(direction) using R+direction without moving",
            "select_tool(tool)",
            "use_tool using Y",
        ]
        landmark = {
            "id": "arrow_firing_position",
            "action": "use_tool",
            "tool": "arrow",
            "action_readiness": {
                "completed": False,
                "position_ready": True,
                "facing_ready": False,
                "next_precondition": "face west",
            },
        }
        self.assertEqual(
            ["select_tool(tool)"],
            ContextBuilder._restrict_fully_ready_landmark_action(
                actions, {"active_landmark": landmark}, selected_tool="bomb"
            ),
        )
        self.assertEqual(
            ["face(direction) using R+direction without moving"],
            ContextBuilder._restrict_fully_ready_landmark_action(
                actions, {"active_landmark": landmark}, selected_tool="arrow"
            ),
        )

    def test_blocked_direction_requires_causal_failed_move(self) -> None:
        builder = ContextBuilder.__new__(ContextBuilder)
        compact = {"x": 28, "y": 30, "blocked_direction": "north"}
        self.assertIsNone(builder._confirmed_blocked_direction(compact, []))
        failed = [{
            "kind": "move",
            "requested_direction": "north",
            "before": {"position": [28, 30]},
            "after": {"position": [28, 30], "blocked_direction": "north"},
        }]
        self.assertEqual("north", builder._confirmed_blocked_direction(compact, failed))
        moved = [{
            **failed[0],
            "after": {"position": [28, 29], "blocked_direction": "north"},
        }]
        self.assertIsNone(builder._confirmed_blocked_direction(compact, moved))

    def test_face_does_not_erase_confirmed_collision_at_same_position(self) -> None:
        compact = {"x": 21, "y": 26, "blocked_direction": "west"}
        failed = {
            "kind": "move",
            "requested_direction": "west",
            "before": {"position": [21, 26]},
            "after": {"position": [21, 26], "blocked_direction": "west"},
            "navigation_relevant_change": False,
        }
        faced = {
            "kind": "face",
            "requested_direction": "north",
            "before": {"position": [21, 26]},
            "after": {"position": [21, 26], "blocked_direction": "west"},
            "navigation_relevant_change": False,
        }
        self.assertEqual(
            "west",
            ContextBuilder._confirmed_blocked_direction(compact, [failed, faced]),
        )

    def test_non_face_action_ends_collision_carryover(self) -> None:
        compact = {"x": 21, "y": 26, "blocked_direction": "west"}
        failed = {
            "kind": "move",
            "requested_direction": "west",
            "before": {"position": [21, 26]},
            "after": {"position": [21, 26], "blocked_direction": "west"},
            "navigation_relevant_change": False,
        }
        interacted = {
            "kind": "interact",
            "requested_direction": "west",
            "before": {"position": [21, 26]},
            "after": {"position": [21, 26], "blocked_direction": "west"},
            "navigation_relevant_change": False,
        }
        self.assertIsNone(
            ContextBuilder._confirmed_blocked_direction(compact, [failed, interacted])
        )

    def test_spatial_correlation_links_wall_collision_to_target_alternative(self) -> None:
        tile_buffer = {
            "cardinal_cells": [
                {"relative": [-1, 0], "live": [20, 26], "family": "structural_a", "occupied": False},
                {"relative": [0, -1], "live": [21, 25], "family": "plain_floor", "occupied": False},
                {"relative": [0, 1], "live": [21, 27], "family": "structural_a", "occupied": False},
            ],
        }
        result = ContextBuilder._spatial_correlation(
            [21, 26], "west", tile_buffer, {"live": [17, 23]}, {"west": "blocked"}
        )
        self.assertIn("curated map marks this edge blocked", result["conclusion"])
        self.assertTrue(result["map_proves_wall_or_block"])
        self.assertEqual([], result["blocked_edge_tests"])
        self.assertEqual(["west", "north"], result["target_components"])
        alternatives = {item["direction"]: item for item in result["local_alternatives"]}
        self.assertEqual({"north", "south", "east"}, set(alternatives))
        self.assertEqual("plain_floor", alternatives["north"]["tile_family"])
        self.assertTrue(alternatives["north"]["target_aligned"])
        self.assertFalse(alternatives["south"]["target_aligned"])

    def test_spatial_correlation_does_not_infer_wall_without_curated_proof(self) -> None:
        tile_buffer = {
            "cardinal_cells": [
                {"relative": [-1, 0], "live": [20, 26], "family": "structural_a", "occupied": False},
                {"relative": [0, -1], "live": [21, 25], "family": "plain_floor", "occupied": False},
                {"relative": [0, 1], "live": [21, 27], "family": "structural_a", "occupied": False},
            ],
        }
        result = ContextBuilder._spatial_correlation(
            [21, 26], "west", tile_buffer, {"live": [17, 23]}, {"west": "partially_known"}
        )
        self.assertIn("is not wall proof", result["conclusion"])
        self.assertFalse(result["map_proves_wall_or_block"])
        self.assertEqual(3, len(result["blocked_edge_tests"]))

    def test_all_dungeon_tools_have_stable_model_ids(self) -> None:
        self.assertEqual(
            ["hook", "bomb", "arrow", "fire_arrow", "hammer"],
            [tool_id for tool_id, _display_name in DUNGEON_TOOLS],
        )

    def test_secret_cave_bridge_uses_proven_mesen_values(self) -> None:
        cave = SecretSkillsCave(None)
        self.assertEqual("active", cave._bridge_state([0x00, 0x02, 0x00]))
        self.assertEqual("inactive", cave._bridge_state([0x02, 0x22, 0x20]))
        self.assertEqual("unknown", cave._bridge_state([0x00, 0x00, 0x00]))

    def test_secret_cave_memory_is_room_scoped(self) -> None:
        cave = SecretSkillsCave(None)
        room_two = cave.established_memory(None, {"id": "room_2"})
        room_three = cave.established_memory(None, {"id": "room_3"})
        self.assertEqual(["room2_north_threshold"], [item["id"] for item in room_two])
        self.assertEqual(
            ["room3_forward_bridge_action", "room3_after_bridge_activation"],
            [item["id"] for item in room_three],
        )
        self.assertEqual([], cave.established_memory(None, {"id": "room_7"}))
        self.assertIn("move west", room_three[1]["then"])

        target = cave.provisional_object_target(None, {"id": "room_4"}, {
            "candidates": [{
                "live": [8, 21], "relative": [4, 2], "family": "obstacle",
            }],
        })
        self.assertEqual([8, 21], target["live"])
        self.assertEqual(["east", "south"], target["direct_distance_reducing_directions"])
        self.assertFalse(target["action_readiness"]["ready"])
        adjacent = cave.provisional_object_target(None, {"id": "room_4"}, {
            "candidates": [{
                "live": [8, 21], "relative": [1, 0], "family": "obstacle",
            }],
        })
        self.assertTrue(adjacent["action_readiness"]["ready"])
        self.assertEqual("east", adjacent["action_readiness"]["direction"])
        self.assertIn("interact(east)", adjacent["action_readiness"]["instruction"])
        self.assertIsNone(cave.provisional_object_target(
            None, {"id": "room_4"}, {"candidates": []}
        ))
        room_four = cave.established_memory(None, {"id": "room_4"})
        self.assertEqual(
            ["room4_floor_button_receiver", "room4_reset_condition"],
            [item["id"] for item in room_four],
        )
        intent = room_four[0]
        self.assertEqual("object_intent", intent["form"])
        self.assertEqual([8, 21], intent["initial_live"])
        self.assertEqual("west", intent["alignment_push_direction"])
        self.assertEqual([4, 20], intent["required_live"])
        self.assertEqual([4, 20], intent["actor_forbidden_live"])
        self.assertEqual(
            [
                [4, 19], [5, 19], [6, 19], [7, 19], [8, 19],
                [4, 21], [5, 21], [6, 21], [7, 21],
            ],
            intent["ephemeral_barrier_live"],
        )
        self.assertEqual([8, 21], intent["opening_push"]["when_object_live"])
        self.assertEqual([8, 22], intent["opening_push"]["actor_target_live"])
        self.assertEqual("north", intent["opening_push"]["interact_direction"])
        self.assertEqual([8, 20], intent["opening_push"]["result_object_live"])
        self.assertEqual([8, 20], intent["alignment_entry"]["when_object_live"])
        self.assertEqual([[9, 21], [9, 20]], intent["alignment_entry"]["actor_route_live"])
        self.assertEqual(
            [[6, 20], [6, 19], [6, 18], [6, 17], [6, 16], [6, 15], [6, 14]],
            intent["solved_exit"]["actor_route_live"],
        )
        self.assertEqual("north", intent["solved_exit"]["transition_direction"])
        self.assertIn("lower foot/base", intent["anchor_semantics"])
        self.assertIn("upper sprite", intent["anchor_semantics"])
        self.assertIn("smaller x is west", intent["coordinate_rule"])
        self.assertIn("smaller y is north", intent["coordinate_rule"])
        self.assertIn("only the pusher", intent["constraint"])
        self.assertIn("intermediate push is not success", intent["constraint"])
        self.assertIn("success iff pillar current_live equals required_live", intent["then"])
        self.assertIn("after any room transition", room_four[1]["then"])

    def test_secret_cave_room_three_target_follows_bridge_phase(self) -> None:
        cave = SecretSkillsCave(None)
        room = {
            "id": "room_3",
            "nearby_live_landmarks": [
                {"id": "return_to_room_2", "live": [28, 33]},
                {"id": "arrow_firing_position", "live": [28, 24]},
                {"id": "bridge_left_side", "live": [21, 26]},
                {"id": "west_door_approach", "live": [17, 23]},
            ],
        }
        wram = bytearray(0x10000)
        for (x, y), value in zip(cave.BRIDGE_TILES, [0x02, 0x22, 0x20]):
            wram[cave.tile_address(x, y)] = value
        mapper = SimpleNamespace(state={"room_history": []})
        observation = SimpleNamespace(wram=bytes(wram), game=SimpleNamespace(x=28))
        target = cave.navigation_target(observation, mapper, room)
        self.assertEqual("arrow_firing_position", target["id"])

        for (x, y), value in zip(cave.BRIDGE_TILES, [0x00, 0x02, 0x00]):
            wram[cave.tile_address(x, y)] = value
        observation = SimpleNamespace(wram=bytes(wram), game=SimpleNamespace(x=28))
        target = cave.navigation_target(observation, mapper, room)
        self.assertEqual("bridge_left_side", target["id"])

        # Standing on a sampled bridge cell can make the raw three-byte state
        # temporarily unknown.  The proven action-landmark completion keeps
        # the crossing target latched instead of regressing to Arrow.
        mapper.state["completed_landmarks"] = {
            "room_3:arrow_firing_position": {"action": "use_tool"}
        }
        for (x, y), value in zip(cave.BRIDGE_TILES, [0x7F, 0x02, 0x00]):
            wram[cave.tile_address(x, y)] = value
        observation = SimpleNamespace(wram=bytes(wram), game=SimpleNamespace(x=24))
        target = cave.navigation_target(observation, mapper, room)
        self.assertEqual("bridge_left_side", target["id"])

        # The buffer scroll can coincidentally reproduce the inactive byte
        # pattern. Completion remains authoritative until record_room_reset
        # explicitly expires this resettable landmark.
        for (x, y), value in zip(cave.BRIDGE_TILES, [0x02, 0x22, 0x20]):
            wram[cave.tile_address(x, y)] = value
        observation = SimpleNamespace(wram=bytes(wram), game=SimpleNamespace(x=28))
        target = cave.navigation_target(observation, mapper, room)
        self.assertEqual("bridge_left_side", target["id"])

        mapper.state["room_history"] = [{"from": "room_8", "to": "room_3"}]
        target = cave.navigation_target(observation, mapper, room)
        self.assertEqual("return_to_room_2", target["id"])

    def test_watchdog_records_live_action_count(self) -> None:
        journal = _Journal()
        gateway = ModelGateway(_Model(), _Watchdog(), journal, _Gate(), action_count=lambda: 7)
        intent = gateway.ask_intent({"goal": "test"}, 4)
        self.assertEqual("wait", intent.kind)
        bark = next(details for event, details in journal.events if event == "model_watchdog_bark")
        self.assertEqual(7, bark["action"])

    def test_openai_transport_wraps_schema_and_honors_role_budget(self) -> None:
        client = LocalModelClient({"planner_max_tokens": 123, "temperature": 0.0})
        client.detect = lambda force=False: {
            "name": "llama_cpp",
            "base_url": "http://127.0.0.1:8080/v1",
            "model": "test-model",
        }
        with patch("agent.model_client.requests.post", return_value=_Response()) as post:
            client._chat(
                [{"role": "user", "content": "test"}],
                role="planner",
                response_format=INTENT_FORMAT,
            )
        payload = post.call_args.kwargs["json"]
        self.assertEqual(123, payload["max_tokens"])
        self.assertEqual("json_schema", payload["response_format"]["type"])
        self.assertIs(INTENT_FORMAT, payload["response_format"]["json_schema"]["schema"])

    def test_vision_uses_schema_on_openai_transport(self) -> None:
        client = LocalModelClient({"enabled": True})
        client.detect = lambda force=False: {
            "name": "llama_cpp",
            "base_url": "http://127.0.0.1:8080/v1",
            "model": "vision-model",
            "capabilities": ["vision"],
        }
        captured = {}

        def fake_chat(messages, role="planner", response_format=None):
            captured.update(role=role, response_format=response_format)
            return json.dumps({
                "scene_type": "dungeon",
                "relevant_objects": [],
                "navigation_hypothesis": "inspect",
                "confidence": 0.5,
                "safe_next_test": "wait",
            })

        client._chat = fake_chat
        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory) / "frame.png"
            frame.write_bytes(b"png")
            client.look(frame, {}, "What is visible?")
        self.assertEqual("vision", captured["role"])
        self.assertIs(VISION_FORMAT, captured["response_format"])
        self.assertEqual(8, VISION_FORMAT["properties"]["relevant_objects"]["maxItems"])
        self.assertTrue(VISION_FORMAT["properties"]["relevant_objects"]["uniqueItems"])

    def test_invalid_optional_vision_response_does_not_abort_run(self) -> None:
        orchestrator = object.__new__(MesenOrchestrator)
        with tempfile.TemporaryDirectory() as directory:
            orchestrator.run_dir = Path(directory)
            orchestrator.actions = 3
            orchestrator.controller = SimpleNamespace(screenshot=lambda: b"png")
            orchestrator.config = {"llm": {"enabled": True}}
            orchestrator.model = SimpleNamespace(
                look=lambda *args, **kwargs: (_ for _ in ()).throw(
                    ValueError("truncated vision JSON")
                )
            )
            orchestrator._context = lambda observation: {"game": {"mode": "exploration"}}
            orchestrator.journal = _Journal()
            orchestrator.short_term_memory = SimpleNamespace(record_perception=lambda *args: None)
            result = orchestrator._look(object(), "What is visible?")
        self.assertEqual("vision_response_invalid", result["status"])
        self.assertIn("WRAM", result["safe_next_test"])

    def test_intent_frames_are_sent_in_chronological_order(self) -> None:
        client = LocalModelClient({"enabled": True})
        captured = {}

        def fake_chat(messages, role="planner", response_format=None):
            captured.update(messages=messages, role=role, response_format=response_format)
            return json.dumps({
                "kind": "wait", "direction": None, "count": 1,
                "question": None, "query": None, "tool": None,
                "rationale": "inspect frames",
            })

        client._chat = fake_chat
        with tempfile.TemporaryDirectory() as directory:
            older = Path(directory) / "older.png"
            newer = Path(directory) / "newer.png"
            older.write_bytes(b"old")
            newer.write_bytes(b"new")
            client.choose_intent({}, 4, frames=[older, newer])
        content = captured["messages"][1]["content"]
        labels = [part["text"] for part in content if part["type"] == "text"][1:]
        self.assertEqual(["Frame 1/2 (PREVIOUS)", "Frame 2/2 (CURRENT)"], labels)
        self.assertEqual("vision", captured["role"])

    def test_intent_schema_is_restricted_to_advertised_actions(self) -> None:
        client = LocalModelClient({"enabled": True})
        captured = {}

        def fake_chat(messages, role="planner", response_format=None):
            captured.update(messages=messages, response_format=response_format)
            return json.dumps({
                "kind": "move", "direction": "north", "count": 1,
                "question": None, "query": None, "tool": None,
                "rationale": "test another edge",
            })

        client._chat = fake_chat
        intent = client.choose_intent({
            "available_actions": [
                "move(direction,count=1..4)",
                "interact(direction optional) using A or direction+A",
            ],
        }, 4)
        self.assertEqual("move", intent.kind)
        self.assertIsNot(INTENT_FORMAT, captured["response_format"])
        self.assertEqual(
            ["move", "interact"],
            captured["response_format"]["properties"]["kind"]["enum"],
        )
        system = captured["messages"][0]["content"]
        self.assertIn("stand on its opposite side", system)
        self.assertIn("same interact may be repeated", system)
        self.assertIn("x increases east and y increases south", system)
        self.assertIn("live_puzzle_overlay", system)
        self.assertIn("Reach T before the stated push", system)
        self.assertIn("checkpoint_move", system)
        self.assertIn("checkpoint_action", system)
        self.assertIn("immediate_phase_feedback", system)
        self.assertIn("look", INTENT_FORMAT["properties"]["kind"]["enum"])

    def test_exploration_inventory_retrieval_has_ten_minute_cooldown(self) -> None:
        orchestrator = object.__new__(MesenOrchestrator)
        orchestrator.config = {"llm": {"exploration_inventory_cooldown_seconds": 600}}
        orchestrator.goal = "test"
        orchestrator.last_exploration_inventory_read = None
        orchestrator.knowledge = SimpleNamespace(search=lambda query: [{"text": query}])
        item = SimpleNamespace(name="Potion", quantity=3)
        observation = SimpleNamespace(
            game=SimpleNamespace(mode="exploration", inventory=(item,))
        )
        first = orchestrator._retrieve(observation, "current inventory")
        second = orchestrator._retrieve(observation, "current inventory")
        self.assertEqual("live_wram_inventory", first[0]["type"])
        self.assertEqual([{"name": "Potion", "quantity": 3}], first[0]["items"])
        self.assertEqual("inventory_cooldown", second[0]["type"])

    def test_short_term_memory_is_retrievable_on_demand(self) -> None:
        orchestrator = object.__new__(MesenOrchestrator)
        orchestrator.short_term_memory = SimpleNamespace(
            recall=lambda: {"recent_actions": [{"kind": "move"}]}
        )
        orchestrator.knowledge = SimpleNamespace(search=lambda query: [])
        observation = SimpleNamespace(game=SimpleNamespace(mode="exploration"))
        result = orchestrator._retrieve(observation, "short term memory")
        self.assertEqual("short_term_memory", result[0]["type"])
        self.assertEqual("move", result[0]["snapshot"]["recent_actions"][0]["kind"])

    def test_consumed_intent_frames_are_deleted(self) -> None:
        orchestrator = object.__new__(MesenOrchestrator)
        with tempfile.TemporaryDirectory() as directory:
            orchestrator.run_dir = Path(directory)
            frame_dir = orchestrator.run_dir / "intent_frames"
            frame_dir.mkdir()
            consumed = frame_dir / "intent_1.png"
            retained = orchestrator.run_dir / "look_1.png"
            consumed.write_bytes(b"temporary")
            retained.write_bytes(b"evidence")
            orchestrator.last_intent_frame = consumed
            orchestrator._cleanup_intent_frames([consumed])
            self.assertFalse(consumed.exists())
            self.assertTrue(retained.exists())
            self.assertIsNone(orchestrator.last_intent_frame)

    def test_existing_run_state_requires_explicit_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            validate_run_directory(run_dir, resume=False)
            (run_dir / "online_navigation_graph.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already contains state"):
                validate_run_directory(run_dir, resume=False)
            validate_run_directory(run_dir, resume=True)

    def test_run_directory_rejects_concurrent_agent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            with run_directory_lock(run_dir):
                with self.assertRaisesRegex(RuntimeError, "already controlled"):
                    with run_directory_lock(run_dir):
                        pass
            with run_directory_lock(run_dir):
                pass

    def test_llama_multimodal_capability_is_accepted_as_vision(self) -> None:
        client = LocalModelClient({"enabled": True})
        client.detect = lambda force=False: {
            "name": "llama_cpp",
            "base_url": "http://127.0.0.1:8080/v1",
            "model": "multimodal-model",
            "capabilities": ["completion", "multimodal"],
        }
        client._chat = lambda *args, **kwargs: json.dumps({
            "scene_type": "dungeon",
            "relevant_objects": [],
            "navigation_hypothesis": "inspect",
            "confidence": 0.5,
            "safe_next_test": "wait",
        })
        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory) / "frame.png"
            frame.write_bytes(b"png")
            result = client.look(frame, {}, "What is visible?")
        self.assertEqual("dungeon", result["scene_type"])

    def test_battle_model_timeout_becomes_controlled_stop(self) -> None:
        journal = _Journal()
        runner = BattleRunner(_StalledBattle(), None, journal, None)
        runner.active = True
        observation = object()
        returned, inputs, stop_reason = runner.step(observation, False, 1, None, 0)
        self.assertIs(observation, returned)
        self.assertEqual(0, inputs)
        self.assertEqual("battle_step_rejected", stop_reason)

    def test_ready_action_landmark_rejects_movement(self) -> None:
        gate = ThinkingGate({"max_thinking_seconds": 120})
        context = {
            "game": {"mode": "exploration", "position": [50, 13]},
            "navigation": {"current_room": {"nearby_live_landmarks": [{
                "id": "switch_south_approach",
                "action": "sword",
                "action_readiness": {
                    "completed": False,
                    "position_ready": True,
                    "facing_ready": True,
                    "next_precondition": None,
                },
            }]}},
            "tile_buffer": {},
        }
        with self.assertRaises(ModelDriftError):
            gate.validate(Intent("move", direction="north"), context, 1.0)
        gate.validate(Intent("sword"), context, 1.0)


if __name__ == "__main__":
    unittest.main()
