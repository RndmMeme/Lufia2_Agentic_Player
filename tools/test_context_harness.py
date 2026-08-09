import tempfile
import unittest
from pathlib import Path

from agent.context_harness import ContextHarness, ModelDriftError, ThinkingGate
from agent.intent import Intent


def raw_context():
    return {
        "goal": "Finish",
        "game": {
            "map_id": 5,
            "map_name": "Secret Skills Cave",
            "zone_name": "Secret Skills Cave",
            "x": 28,
            "y": 42,
            "direction": "north",
            "blocked_direction": None,
            "mode": "exploration",
            "dialog_active": False,
            "gold": 10,
            "party": [{"name": "Guy", "status": 0, "hp": 10, "max_hp": 20, "mp": 3, "ip": 4}],
            "enemies": [],
            "progression_items": ["Bomb"],
            "inventory": [{"name": "noise"}] * 100,
            "event_flags": "ff" * 100,
        },
        "strategic_progression": {"target": "next"},
        "dungeon_context": {"dungeon": "Secret Skills Cave"},
        "navigation": {"suggested_direction": None},
        "recent_events": [],
    }


class ContextHarnessTests(unittest.TestCase):
    def test_room_reset_clears_prompt_summary_and_intent_loop_state(self):
        with tempfile.TemporaryDirectory() as directory:
            harness = ContextHarness({"max_prompt_chars": 3000}, Path(directory))
            harness.summary["recent_outcomes"] = [{"outcome": "blocked_now"}]
            harness.summary["blocked_counts"] = {"[1,2]:north": 3}
            harness.reset_room_episode()
            self.assertEqual([], harness.summary["recent_outcomes"])
            self.assertEqual({}, harness.summary["blocked_counts"])

            gate = ThinkingGate({})
            gate._last_signature = "stale-intent"
            gate._last_fingerprint = (5, (1, 2))
            gate._repeat_count = 2
            gate.reset_room_episode()
            self.assertIsNone(gate._last_signature)
            self.assertIsNone(gate._last_fingerprint)
            self.assertEqual(0, gate._repeat_count)

    def test_reset_room_episode_reaches_exploration_prompt(self):
        raw = raw_context()
        raw["room_episode"] = {
            "generation": 2,
            "origin": "reset_room",
            "puzzle_status": "unsolved",
            "perception_status": "fresh_observation_required",
            "intent_status": "none",
        }
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 3000}, Path(directory)).compact(raw)
        self.assertEqual("unsolved", compact["room_episode"]["puzzle_status"])
        self.assertEqual("none", compact["room_episode"]["intent_status"])

    def test_compacts_noise_and_persists_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 3000}, Path(directory)).compact(raw_context())
            self.assertNotIn("inventory", compact["game"])
            self.assertLessEqual(compact["context_budget"]["chars"], 3000)
            self.assertTrue((Path(directory) / "context_summary.json").exists())

    def test_exploration_context_omits_irrelevant_state(self):
        raw = raw_context()
        raw["game"].update({
            "zone_id": 5,
            "previous_direction": "west",
            "blocked_direction": "north",
        })
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 3000}, Path(directory)).compact(raw)
        game = compact["game"]
        self.assertEqual([28, 42], game["position"])
        self.assertEqual("west", game["previous_direction"])
        self.assertEqual("north", game["blocked_direction"])
        for noisy in ("party", "enemies", "gold", "progression_items", "inventory"):
            self.assertNotIn(noisy, game)
        self.assertNotIn("dialog_active", game)
        for redundant in ("feedback", "episode_summary", "recent_events", "dungeon_context"):
            self.assertNotIn(redundant, compact)

    def test_exploration_context_stays_small_with_redundant_history(self):
        raw = raw_context()
        raw.update({
            "navigation_map": {
                "available": True,
                "ascii_crop": "\n".join([f"{y:02d} " + "." * 19 for y in range(19)]),
                "nearby_curated_markers": [{"type": "door", "notes": "x" * 100}] * 16,
            },
            "navigation": {
                "current_room": {
                    "id": "room_3", "objective": "Reach the west door",
                    "success_evidence": "Transit reached",
                    "nearby_live_landmarks": [
                        {"id": f"target_{index}", "live": [index, index],
                         "derived_relation": {"manhattan_tiles": index}}
                        for index in range(8)
                    ],
                },
                "progress": {"room_history": [{"from": "a", "to": "b"}] * 40},
            },
            "feedback": {"recent": [{"feedback": "noise" * 100}] * 6},
            "recent_events": [{"index": index, "outcome": "open"} for index in range(20)],
            "reasoning_evidence": [{"type": "look", "result": "evidence" * 100}],
            "memory_access": {"available": True, "query": "short term memory"},
        })
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 10500}, Path(directory)).compact(raw)
            self.assertLess(compact["context_budget"]["chars"], 7000)
            self.assertEqual(3, len(compact["navigation"]["current_room"]["reference_landmarks"]))
            self.assertTrue((Path(directory) / "prompt_stats.jsonl").exists())

    def test_dialog_and_battle_fields_are_mode_gated(self):
        raw = raw_context()
        raw["game"]["dialog_active"] = True
        with tempfile.TemporaryDirectory() as directory:
            dialog = ContextHarness({"max_prompt_chars": 3000}, Path(directory)).compact(raw)
        self.assertTrue(dialog["game"]["dialog_active"])

        raw["game"]["mode"] = "battle"
        with tempfile.TemporaryDirectory() as directory:
            battle = ContextHarness({"max_prompt_chars": 3000}, Path(directory)).compact(raw)
        self.assertIn("party", battle["game"])
        self.assertIn("enemies", battle["game"])

    def test_action_linked_world_change_survives_context_compaction(self):
        raw = raw_context()
        raw["tile_buffer"] = {
            "available": True,
            "role": "ACTOR_LOCAL_3X3",
            "center_live": [28, 24],
            "rows": ["...", ".@.", "..."],
            "cardinal_cells": [],
        }
        raw["navigation"] = {
            "confirmed_world_changes": [{
                "source_landmark": "arrow_firing_position",
                "effect_region_after": {
                    "role": "POST_ACTION_EFFECT_REGION",
                    "center_live": [24, 27],
                    "rows": ["...", ".O.", "..."],
                },
            }],
        }
        raw["recent_agent_actions"] = [{
            "kind": "use_tool",
            "before": {"position": [28, 24], "direction": "west"},
            "after": {"position": [28, 24], "direction": "west"},
            "feedback": {"delta": 12, "feedback": "Strong success"},
            "map_tile_change_count": 3,
            "map_tile_changes": [
                {"live": [24, 26]}, {"live": [24, 27]}, {"live": [24, 28]},
            ],
            "map_effect_region_after": {
                "role": "POST_ACTION_EFFECT_REGION",
                "center_live": [24, 27],
                "rows": ["...", ".O.", "..."],
            },
            "completed_landmark": {"landmark_id": "arrow_firing_position"},
        }]
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 3000}, Path(directory)).compact(raw)
        change = compact["recent_agent_actions"][-1]["confirmed_world_change"]
        self.assertEqual("arrow_firing_position", change["completed_landmark"])
        self.assertEqual("navigation.confirmed_world_changes", change["effect_reference"])
        self.assertEqual("ACTOR_LOCAL_3X3", compact["tile_buffer"]["role"])
        effect = compact["navigation"]["confirmed_world_changes"][0]["effect_region_after"]
        self.assertEqual("POST_ACTION_EFFECT_REGION", effect["role"])

    def test_visible_object_candidates_survive_exploration_compaction(self):
        raw = raw_context()
        raw["visible_object_candidates"] = {
            "available": True,
            "role": "ACTOR_LOCAL_DYNAMIC_TILE_CANDIDATES",
            "radius": 4,
            "candidates": [{
                "live": [8, 21], "relative": [4, 3],
                "manhattan_tiles": 7, "family": "obstacle",
            }],
            "policy": "candidate, not identity",
        }
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 5000}, Path(directory)).compact(raw)
        candidate = compact["visible_object_candidates"]["candidates"][0]
        self.assertEqual([8, 21], candidate["live"])
        self.assertEqual("obstacle", candidate["family"])

    def test_established_memory_survives_without_run_history(self):
        raw = raw_context()
        raw["established_memory"] = {
            "policy": "established only",
            "global": [{"id": "threshold_is_not_room_entry", "form": "binary"}],
            "dungeon": [{"id": "room2_north_threshold", "form": "binary"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 5000}, Path(directory)).compact(raw)
        memory = compact["established_memory"]
        self.assertEqual("threshold_is_not_room_entry", memory["global"][0]["id"])
        self.assertEqual("room2_north_threshold", memory["dungeon"][0]["id"])

    def test_provisional_object_target_becomes_current_step(self):
        raw = raw_context()
        raw["navigation"] = {
            "current_room": {"id": "room_4", "objective": "Push the pillar"},
            "provisional_object_target": {
                "id": "room4_initial_pillar_candidate",
                "live": [8, 21],
                "relative": [4, 2],
                "identity": "established_initial_pillar_candidate",
                "direct_distance_reducing_directions": ["east", "south"],
                "status": "contact-test",
                "success_evidence": "actor and map displacement",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 5000}, Path(directory)).compact(raw)
        target = compact["navigation"]["provisional_object_target"]
        self.assertEqual([8, 21], target["live"])
        self.assertEqual([8, 21], compact["task_progress"]["current_step"]["target"])
        self.assertEqual(
            "established_initial_pillar_candidate",
            compact["task_progress"]["current_step"]["target_type"],
        )

    def test_task_progress_separates_completed_goal_clause_from_current_step(self):
        raw = raw_context()
        raw["navigation"] = {
            "active_landmark": {
                "id": "bridge_left_side", "live": [21, 26],
                "selection_reason": "bridge activated; cross west",
            },
            "confirmed_world_changes": [{
                "source_landmark": "arrow_firing_position",
                "effect": {"message": "Bridge activated; do not shoot again."},
            }],
            "current_room": {"id": "room_3", "nearby_live_landmarks": []},
        }
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 5000}, Path(directory)).compact(raw)
        self.assertEqual("arrow_firing_position", compact["task_progress"]["completed_steps"][0]["landmark"])
        self.assertEqual("bridge_left_side", compact["task_progress"]["current_step"]["landmark"])

    def test_unclassified_world_change_is_intermediate_not_completed(self):
        raw = raw_context()
        raw["navigation"] = {
            "confirmed_world_changes": [{
                "source_landmark": "observed_world_change",
                "effect": {"message": "A push changed two map tiles."},
            }],
            "current_room": {
                "id": "room_4",
                "objective": "Push the pillar onto its switch.",
                "success_evidence": "The door opens.",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 5000}, Path(directory)).compact(raw)
        self.assertEqual([], compact["task_progress"]["completed_steps"])
        self.assertEqual(
            "puzzle state changed; objective completion not yet proven",
            compact["task_progress"]["observed_state_changes"][0]["status"],
        )
        self.assertEqual(
            "Push the pillar onto its switch.",
            compact["task_progress"]["current_step"]["objective"],
        )

    def test_tracked_object_position_becomes_current_step_target(self):
        raw = raw_context()
        raw["established_memory"] = {
            "dungeon": [{
                "form": "object_intent",
                "alignment_waypoint_live": [4, 21],
                "alignment_push_direction": "west",
                "required_live": [4, 20],
                "actor_forbidden_live": [4, 20],
                "final_alignment": {
                    "when_object_live": [4, 21],
                    "actor_target_live": [4, 22],
                    "interact_direction": "north",
                },
            }],
        }
        raw["navigation"] = {
            "tracked_movable_object": {
                "estimated_live": [8, 19],
                "action_readiness": {
                    "ready": True,
                    "action": "interact",
                    "direction": "south",
                },
            },
            "current_room": {
                "id": "room_4",
                "objective": "Solve the pillar puzzle.",
                "success_evidence": "The pillar itself visibly occupies the separate floor button.",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 5000}, Path(directory)).compact(raw)
        step = compact["task_progress"]["current_step"]
        self.assertEqual([9, 19], step["target"])
        self.assertEqual("actor_position_for_push", step["target_type"])
        self.assertEqual([8, 19], step["object_current_live"])
        self.assertTrue(step["action_readiness"]["ready"])
        self.assertEqual("south", step["action_readiness"]["direction"])
        self.assertEqual([4, 21], step["required_object_live"])
        self.assertEqual("west", step["useful_push_direction"])
        self.assertEqual("east of the object", step["required_push_side"])
        self.assertEqual([4, 20], step["actor_forbidden_live"])
        self.assertNotIn("final_alignment", step)
        self.assertEqual([], compact["established_memory"]["dungeon"])

    def test_initial_object_intent_gets_push_checkpoint_without_detector_candidate(self):
        raw = raw_context()
        raw["position_update"] = {
            "current": [14, 23],
            "coordinate_rule": "x increases east; y increases south",
        }
        raw["established_memory"] = {"dungeon": [{
            "form": "object_intent",
            "initial_live": [8, 21],
            "alignment_push_direction": "west",
            "required_live": [4, 20],
            "ephemeral_barrier_live": [
                [5, 20], [6, 20], [7, 20], [8, 20],
                [5, 22], [6, 22], [7, 22], [8, 22],
            ],
        }]}
        raw["navigation"] = {
            "current_room": {"id": "room_4", "objective": "Solve the pillar puzzle."},
        }
        raw["navigation_map"] = {
            "available": True,
            "coordinate_bounds": {"min_x": 3, "max_x": 15, "min_y": 19, "max_y": 24},
            "ascii_crop": "\n".join([f"{y:02d} " + "." * 13 for y in range(19, 25)]),
        }
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 8000}, Path(directory)).compact(raw)

        overlay = compact["navigation_map"]["live_puzzle_overlay"]
        self.assertEqual([9, 21], compact["task_progress"]["current_step"]["target"])
        self.assertEqual("actor_position_for_push", compact["task_progress"]["current_step"]["target_type"])
        self.assertEqual([8, 21], overlay["entities"]["object_live"])
        self.assertEqual([9, 21], overlay["entities"]["next_stance_live"])
        self.assertEqual(2, overlay["rows"].count("#  #  #  #"))
        self.assertIn("temporary puzzle wall", overlay["legend"])
        self.assertIn("established movable object", compact["task_progress"]["current_step"]["objective"])

        raw["position_update"]["current"] = [9, 21]
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 8000}, Path(directory)).compact(raw)
        self.assertEqual(
            {"kind": "interact", "direction": "west"},
            compact["task_progress"]["current_step"]["checkpoint_action"],
        )

    def test_opening_push_switches_once_from_north_to_west_corridor(self):
        intent = {
            "form": "object_intent",
            "initial_live": [8, 21],
            "alignment_push_direction": "west",
            "required_live": [4, 20],
            "opening_push": {
                "when_object_live": [8, 21],
                "actor_target_live": [8, 22],
                "interact_direction": "north",
                "result_object_live": [8, 20],
            },
            "alignment_entry": {
                "when_object_live": [8, 20],
                "actor_route_live": [[9, 21], [9, 20]],
            },
        }

        def compact_for(actor, movable=None):
            raw = raw_context()
            raw["position_update"] = {"current": actor}
            raw["established_memory"] = {"dungeon": [intent]}
            raw["navigation"] = {
                "current_room": {"id": "room_4", "objective": "Solve the pillar puzzle."},
            }
            if movable is not None:
                raw["navigation"]["tracked_movable_object"] = {"estimated_live": movable}
            with tempfile.TemporaryDirectory() as directory:
                return ContextHarness({"max_prompt_chars": 8000}, Path(directory)).compact(raw)

        step = compact_for([8, 22])["task_progress"]["current_step"]
        self.assertEqual([8, 22], step["target"])
        self.assertEqual({"kind": "interact", "direction": "north"}, step["checkpoint_action"])

        after_opening = compact_for([8, 21], [8, 20])["task_progress"]
        step = after_opening["current_step"]
        self.assertEqual([9, 21], step["target"])
        self.assertEqual({"direction": "east", "count": 1}, step["checkpoint_move"])
        feedback = after_opening["immediate_phase_feedback"]
        self.assertEqual("success", feedback["status"])
        self.assertIn("North push succeeded once", feedback["message"])
        self.assertIn("Move east 1 tile(s) now", feedback["message"])
        self.assertEqual("interact(north)", feedback["completed_once"])
        self.assertEqual("interact(north)", feedback["not_advised"])
        self.assertEqual([8, 20], feedback["object_after_live"])
        self.assertEqual([9, 21], feedback["next_actor_target_live"])

        step = compact_for([9, 21], [8, 20])["task_progress"]["current_step"]
        self.assertEqual([9, 20], step["target"])
        self.assertEqual({"direction": "north", "count": 1}, step["checkpoint_move"])

        step = compact_for([9, 20], [8, 20])["task_progress"]["current_step"]
        self.assertEqual({"kind": "interact", "direction": "west"}, step["checkpoint_action"])

        step = compact_for([8, 20], [7, 20])["task_progress"]["current_step"]
        self.assertEqual({"kind": "interact", "direction": "west"}, step["checkpoint_action"])

    def test_object_alignment_checkpoint_becomes_current_actor_step(self):
        raw = raw_context()
        raw["position_update"] = {
            "current": [5, 21],
            "coordinate_rule": "x increases east; y increases south",
            "tracked_movable_object": {"estimated_live": [4, 21]},
        }
        raw["established_memory"] = {"dungeon": [{
            "form": "object_intent",
            "required_live": [4, 20],
            "anchor_semantics": "pillar lower foot/base tile",
            "final_alignment": {
                "when_object_live": [4, 21],
                "actor_route_live": [[5, 22], [4, 22]],
                "actor_target_live": [4, 22],
                "interact_direction": "north",
            },
        }]}
        raw["navigation_map"] = {
            "available": True,
            "coordinate_bounds": {"min_x": 3, "max_x": 6, "min_y": 19, "max_y": 23},
            "ascii_crop": "\n".join([f"{y:02d} ...." for y in range(19, 24)]),
        }
        raw["navigation"] = {
            "tracked_movable_object": {
                "estimated_live": [4, 21],
                "action_readiness": "ready",
            },
            "current_room": {
                "id": "room_4",
                "objective": "Solve the pillar puzzle.",
                "success_evidence": "The pillar itself visibly occupies the separate floor button.",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 5000}, Path(directory)).compact(raw)

        step = compact["task_progress"]["current_step"]
        self.assertEqual([5, 22], step["target"])
        self.assertEqual("actor_route_waypoint", step["target_type"])
        self.assertEqual([4, 21], step["object_current_live"])
        self.assertEqual([0, 1], step["delta_from_actor"])
        self.assertEqual({"direction": "south", "count": 1}, step["checkpoint_move"])
        self.assertNotIn("checkpoint_action", step)
        self.assertEqual("move(south, count=1)", step["action_now"])
        self.assertIn("regenerate", step["then"])
        self.assertIn("pillar itself", step["success_evidence"])
        self.assertIn("do not interact", step["status"])
        self.assertNotIn("tracked_movable_object", compact["navigation"])
        self.assertNotIn("tracked_movable_object", compact["position_update"])
        overlay = compact["navigation_map"]["live_puzzle_overlay"]
        self.assertEqual([5, 21], overlay["entities"]["actor_live"])
        self.assertEqual([4, 21], overlay["entities"]["object_live"])
        self.assertEqual([4, 20], overlay["entities"]["receiver_live"])
        self.assertEqual([5, 22], overlay["entities"]["next_stance_live"])
        self.assertFalse(overlay["entities"]["actor_at_next_stance"])
        self.assertFalse(overlay["entities"]["object_on_receiver"])
        self.assertIn("S", overlay["rows"])
        self.assertIn("P", overlay["rows"])
        self.assertIn("T", overlay["rows"])
        self.assertIn("@", overlay["rows"])
        self.assertEqual("pillar lower foot/base tile", overlay["anchor_semantics"])
        self.assertIn("discard after this model decision", overlay["lifetime"])

        raw["position_update"]["current"] = [5, 22]
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 5000}, Path(directory)).compact(raw)
        step = compact["task_progress"]["current_step"]
        self.assertEqual([4, 22], step["target"])
        self.assertEqual("actor_position_for_final_push", step["target_type"])
        self.assertEqual([-1, 0], step["delta_from_actor"])
        self.assertEqual({"direction": "west", "count": 1}, step["checkpoint_move"])
        self.assertNotIn("checkpoint_action", step)
        self.assertEqual("move(west, count=1)", step["action_now"])
        self.assertEqual("at target, use interact(north) exactly once", step["then"])
        overlay = compact["navigation_map"]["live_puzzle_overlay"]
        self.assertEqual([4, 22], overlay["entities"]["next_stance_live"])

        raw["position_update"]["current"] = [4, 22]
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 5000}, Path(directory)).compact(raw)
        step = compact["task_progress"]["current_step"]
        self.assertEqual([0, 0], step["delta_from_actor"])
        self.assertEqual(
            {"kind": "interact", "direction": "north"},
            step["checkpoint_action"],
        )
        self.assertNotIn("checkpoint_move", step)
        self.assertEqual("interact(north) exactly once", step["action_now"])
        self.assertIsNone(step["then"])
        overlay = compact["navigation_map"]["live_puzzle_overlay"]
        self.assertTrue(overlay["entities"]["actor_at_next_stance"])

    def test_completed_object_target_switches_to_exit_verification(self):
        raw = raw_context()
        raw["established_memory"] = {"dungeon": [{
            "form": "object_intent",
            "alignment_waypoint_live": [4, 21],
            "required_live": [4, 20],
            "solved_exit": {
                "actor_route_live": [
                    [6, 20], [6, 19], [6, 18], [6, 17],
                    [6, 16], [6, 15], [6, 14],
                ],
                "transition_direction": "north",
            },
        }]}
        raw["navigation"] = {
            "tracked_movable_object": {"estimated_live": [4, 20]},
            "current_room": {
                "id": "room_4",
                "success_evidence": "The north door opens.",
            },
        }
        raw["position_update"] = {
            "current": [5, 20],
            "tracked_movable_object": {"estimated_live": [4, 20]},
        }
        raw["navigation_map"] = {
            "available": True,
            "coordinate_bounds": {"min_x": 3, "max_x": 6, "min_y": 19, "max_y": 22},
            "ascii_crop": "\n".join([f"{y:02d} ...." for y in range(19, 23)]),
        }
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 5000}, Path(directory)).compact(raw)

        step = compact["task_progress"]["current_step"]
        self.assertIn("opened exit", step["objective"])
        self.assertIn("do not push", step["status"])
        self.assertEqual([6, 20], step["target"])
        self.assertEqual({"direction": "east", "count": 1}, step["checkpoint_move"])
        self.assertNotIn("tracked_movable_object", compact["navigation"])
        self.assertNotIn("tracked_movable_object", compact["position_update"])
        overlay = compact["navigation_map"]["live_puzzle_overlay"]
        self.assertTrue(overlay["entities"]["object_on_receiver"])
        self.assertIsNone(overlay["entities"]["next_stance_live"])
        self.assertNotIn("temporary_barriers_live", overlay["entities"])
        self.assertIn("*", overlay["rows"])

    def test_tracked_object_replaces_stale_provisional_candidate(self):
        raw = raw_context()
        raw["navigation"] = {
            "tracked_movable_object": {"estimated_live": [7, 21]},
            "provisional_object_target": {
                "id": "room4_initial_pillar_candidate",
                "live": [8, 21],
            },
            "current_room": {"id": "room_4", "objective": "Solve the pillar puzzle."},
        }
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 5000}, Path(directory)).compact(raw)
        self.assertEqual([7, 21], compact["navigation"]["tracked_movable_object"]["estimated_live"])
        self.assertNotIn("provisional_object_target", compact["navigation"])
        self.assertEqual([7, 21], compact["task_progress"]["current_step"]["target"])

    def test_task_progress_uses_transit_continuation_checkpoint(self):
        raw = raw_context()
        raw["navigation"] = {
            "active_landmark": {
                "id": "west_door_approach",
                "live": [17, 23],
                "effective_live": [17, 21],
                "selection_reason": "continue through the door",
                "traversal": {
                    "phase": "crossing_threshold",
                    "direction": "north",
                    "next_step": "continue north through the threshold",
                },
                "checkpoint": {
                    "id": "west_door_approach",
                    "type": "traversal",
                    "status": "crossing_threshold",
                },
            },
            "current_room": {"id": "room_3", "nearby_live_landmarks": []},
        }
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 5000}, Path(directory)).compact(raw)
        step = compact["task_progress"]["current_step"]
        self.assertEqual([17, 21], step["target"])
        self.assertEqual("crossing_threshold", step["traversal_phase"])
        self.assertEqual("continue through the door", step["reason"])

    def test_completed_transit_segment_releases_local_navigation(self):
        raw = raw_context()
        raw["navigation"] = {
            "completed_traversal_segment": {
                "id": "west_door_approach",
                "status": "segment_boundary_reached",
                "success": "straight transit segment ended",
            },
            "current_room": {
                "id": "room_3",
                "objective": "Continue through the local transit area.",
                "nearby_live_landmarks": [{
                    "id": "west_door_approach",
                    "live": [17, 23],
                    "completed": True,
                }],
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 5000}, Path(directory)).compact(raw)
        self.assertIsNone(compact["task_progress"]["current_step"])
        self.assertEqual(
            "west_door_approach",
            compact["task_progress"]["completed_steps"][0]["landmark"],
        )
        self.assertEqual(
            "segment_boundary_reached",
            compact["navigation"]["completed_traversal_segment"]["status"],
        )

    def test_unresolved_transit_keeps_live_policy_without_stale_map(self):
        raw = raw_context()
        raw["navigation_map"] = {
            "available": False,
            "reason": "previous room map suppressed",
            "local_policy": "use live local evidence",
            "nearby_curated_markers": [],
        }
        raw["navigation"] = {
            "completed_traversal_segment": {
                "id": "west_door_approach",
                "status": "segment_boundary_reached",
            },
            "local_layout_resolution": {
                "status": "unresolved_after_transit",
                "stale_context_suppressed": True,
            },
            "local_route_evidence": {
                "scope": "current coordinate",
                "passable": [{"direction": "east"}],
                "impassable_now": [{"direction": "west"}],
                "untried": ["south"],
            },
            "current_room": {
                "id": None,
                "resolved": False,
                "objective": "Explore the current local layout and find a passable exit.",
                "nearby_live_landmarks": [],
            },
        }
        raw["available_actions"] = [
            "move(direction,count=1..4)",
            "look at current frame",
        ]
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 5000}, Path(directory)).compact(raw)
        self.assertFalse(compact["navigation_map"]["available"])
        self.assertEqual(
            "previous room map suppressed", compact["navigation_map"]["reason"]
        )
        self.assertNotIn("ascii_crop", compact["navigation_map"])
        self.assertEqual(
            "unresolved_after_transit",
            compact["navigation"]["local_layout_resolution"]["status"],
        )
        self.assertEqual(
            "east",
            compact["navigation"]["local_route_evidence"]["passable"][0]["direction"],
        )
        self.assertEqual([], compact["navigation"]["current_room"]["reference_landmarks"])

    def test_thinking_gate_rejects_repeat_without_state_change(self):
        with tempfile.TemporaryDirectory() as directory:
            context = ContextHarness({"max_prompt_chars": 3000}, Path(directory)).compact(raw_context())
        gate = ThinkingGate({"max_same_intent_without_change": 2})
        intent = Intent("interact")
        gate.validate(intent, context, 1)
        gate.validate(intent, context, 1)
        with self.assertRaises(ModelDriftError):
            gate.validate(intent, context, 1)

    def test_thinking_gate_rejects_configured_limit(self):
        gate = ThinkingGate({"max_thinking_seconds": 270})
        context = {"game": {"map_id": 1, "position": [1, 1], "mode": "exploration", "progression_items": []}}
        with self.assertRaises(ModelDriftError):
            gate.validate(Intent("interact"), context, 270.1)

    def test_thinking_gate_rejects_redundant_facing(self):
        gate = ThinkingGate({"max_thinking_seconds": 270})
        context = {"game": {"map_id": 5, "position": [1, 1], "direction": "north", "mode": "exploration", "progression_items": []}}
        with self.assertRaises(ModelDriftError):
            gate.validate(Intent("face", direction="north"), context, 1)

    def test_large_navigation_context_is_trimmed_without_losing_room_objective(self):
        raw = raw_context()
        raw["navigation"] = {
            "current_room": {
                "id": "room_3",
                "objective": "Solve the arrow bridge.",
                "nearby_live_landmarks": [
                    {"id": f"landmark_{index}", "relative": [index, index]}
                    for index in range(20)
                ],
            },
            "progress": {
                "objective": "duplicate goal " * 100,
                "room_history": [{"from": index, "to": index + 1} for index in range(30)],
            },
        }
        raw["strategic_progression"] = {"accessible": ["place"] * 200}
        with tempfile.TemporaryDirectory() as directory:
            compact = ContextHarness({"max_prompt_chars": 3000}, Path(directory)).compact(raw)
        self.assertEqual(compact["navigation"]["current_room"]["objective"], "Solve the arrow bridge.")
        self.assertLessEqual(compact["context_budget"]["chars"], 3000)

    def test_thinking_gate_rejects_leaving_an_active_action_landmark(self):
        gate = ThinkingGate({"max_thinking_seconds": 270})
        context = {
            "game": {
                "map_id": 5, "position": [28, 24], "direction": "south",
                "mode": "exploration", "progression_items": [],
            },
            "navigation": {"current_room": {"nearby_live_landmarks": [{
                "id": "arrow_firing_position",
                "action": "use_tool",
                "action_readiness": {
                    "position_ready": True,
                    "required_facing": "west",
                    "next_precondition": "face west",
                },
            }]}},
            "selected_dungeon_tool": "arrow",
        }
        with self.assertRaisesRegex(ModelDriftError, "leave active action landmark"):
            gate.validate(Intent("move", direction="south"), context, 1)
        gate.validate(Intent("face", direction="west"), context, 1)

    def test_thinking_gate_allows_backtracking_away_from_active_landmark(self):
        gate = ThinkingGate({"max_thinking_seconds": 270})
        context = {
            "game": {
                "map_id": 5, "position": [28, 29], "direction": "north",
                "blocked_direction": None, "mode": "exploration", "progression_items": [],
            },
            "navigation": {
                "active_landmark": {"id": "arrow_firing_position", "live": [28, 24]},
                "current_room": {"nearby_live_landmarks": []},
            },
        }
        gate.validate(Intent("move", direction="south"), context, 1)
        gate.validate(Intent("move", direction="north"), context, 1)
        gate.validate(Intent("move", direction="east"), context, 1)

    def test_thinking_gate_allows_detour_when_direct_axis_is_blocked(self):
        gate = ThinkingGate({"max_thinking_seconds": 270})
        context = {
            "game": {
                "map_id": 5, "position": [28, 29], "direction": "north",
                "blocked_direction": "north", "mode": "exploration", "progression_items": [],
            },
            "navigation": {
                "active_landmark": {"id": "arrow_firing_position", "live": [28, 24]},
                "current_room": {"nearby_live_landmarks": []},
            },
        }
        gate.validate(Intent("move", direction="south"), context, 1)

    def test_thinking_gate_rejects_unavailable_dungeon_tool(self):
        gate = ThinkingGate({"max_thinking_seconds": 270})
        context = {
            "game": {"map_id": 5, "position": [1, 1], "mode": "exploration"},
            "exploration_relevant_items": [
                {"name": "arrow", "available": True, "selected": False},
                {"name": "hammer", "available": False, "selected": False},
            ],
            "navigation": {"current_room": {"nearby_live_landmarks": []}},
        }
        gate.validate(Intent("select_tool", tool="arrow"), context, 1)
        with self.assertRaisesRegex(ModelDriftError, "unavailable dungeon tool"):
            gate.validate(Intent("select_tool", tool="hammer"), context, 1)

    def test_thinking_gate_rejects_unadvertised_perception(self):
        gate = ThinkingGate({"max_thinking_seconds": 270})
        context = {
            "game": {"map_id": 5, "position": [28, 30], "mode": "exploration"},
            "available_actions": ["move(direction,count=1..4)", "face(direction)"],
            "navigation": {"current_room": {"nearby_live_landmarks": []}},
        }
        with self.assertRaisesRegex(ModelDriftError, "unavailable action look"):
            gate.validate(Intent("look"), context, 1)

    def test_thinking_gate_rejects_model_initiated_room_reset(self):
        gate = ThinkingGate({"max_thinking_seconds": 270})
        context = {
            "game": {"map_id": 5, "position": [17, 20], "mode": "exploration"},
            "available_actions": ["move(direction,count=1..4)", "face(direction)"],
            "navigation": {"current_room": {"nearby_live_landmarks": []}},
        }
        with self.assertRaisesRegex(ModelDriftError, "unavailable action reset_room"):
            gate.validate(Intent("reset_room"), context, 1)

    def test_thinking_gate_requires_recovery_ticket_even_if_reset_is_advertised(self):
        gate = ThinkingGate({"max_thinking_seconds": 270})
        context = {
            "game": {"map_id": 5, "position": [7, 21], "mode": "exploration"},
            "available_actions": ["reset_room (conditional puzzle recovery)"],
            "room_reset_recovery": {"eligible": False},
            "navigation": {"current_room": {"nearby_live_landmarks": []}},
        }
        with self.assertRaisesRegex(ModelDriftError, "no current curated recovery ticket"):
            gate.validate(Intent("reset_room"), context, 1)
        context["room_reset_recovery"]["eligible"] = True
        gate.validate(Intent("reset_room"), context, 1)

    def test_thinking_gate_rejects_same_no_effect_directed_interact_at_same_tile(self):
        gate = ThinkingGate({"max_thinking_seconds": 270})
        context = {
            "game": {"map_id": 5, "position": [4, 18], "mode": "exploration"},
            "available_actions": ["interact(direction optional)"],
            "recent_agent_actions": [{
                "kind": "interact",
                "requested_direction": "north",
                "from": [4, 18],
                "to": [4, 18],
                "feedback": "no confirmed effect",
            }],
            "navigation": {"current_room": {"nearby_live_landmarks": []}},
        }
        with self.assertRaisesRegex(ModelDriftError, "already had no effect"):
            gate.validate(Intent("interact", direction="north"), context, 1)
        gate.validate(Intent("move", direction="east"), {
            **context,
            "available_actions": ["move(direction,count=1..4)"],
        }, 1)

    def test_thinking_gate_enforces_dungeon_tool_landmark_preconditions(self):
        gate = ThinkingGate({"max_thinking_seconds": 270})
        context = {
            "game": {"map_id": 5, "position": [28, 29], "mode": "exploration"},
            "selected_dungeon_tool": "arrow",
            "available_actions": ["move(direction,count=1..4)", "interact(direction optional)", "use_tool using Y"],
            "navigation": {
                "active_landmark": {
                    "id": "arrow_firing_position", "action": "use_tool",
                    "action_readiness": {
                        "completed": False, "position_ready": False,
                        "facing_ready": False, "required_facing": "west",
                    },
                },
                "current_room": {"nearby_live_landmarks": []},
            },
        }
        with self.assertRaisesRegex(ModelDriftError, "requires reaching"):
            gate.validate(Intent("use_tool", rationale="shoot arrow"), context, 1)
        with self.assertRaisesRegex(ModelDriftError, "interact presses A"):
            gate.validate(Intent("interact", direction="west", rationale="shoot arrow"), context, 1)
        gate.validate(Intent("move", direction="north"), context, 1)

        readiness = context["navigation"]["active_landmark"]["action_readiness"]
        readiness.update(position_ready=True, facing_ready=True)
        gate.validate(Intent("use_tool", rationale="shoot arrow"), context, 1)

    def test_spatial_correlation_does_not_override_available_actions(self):
        gate = ThinkingGate({"max_thinking_seconds": 270})
        context = {
            "game": {"map_id": 5, "position": [21, 26], "mode": "exploration"},
            "available_actions": ["move(direction,count=1..4)"],
            "spatial_correlation": {
                "conclusion": "Plain movement west is impassable now; cause unknown.",
                "target": [17, 23],
                "target_components": ["west", "north"],
                "local_alternatives": [{
                    "direction": "north", "tile_family": "plain_floor", "occupied": False,
                }, {
                    "direction": "south", "tile_family": "structural_a", "occupied": False,
                }],
                "blocked_edge_tests": ["interact west (direction+A)"],
            },
            "navigation": {"current_room": {"nearby_live_landmarks": []}},
        }
        with self.assertRaisesRegex(ModelDriftError, "unavailable action look"):
            gate.validate(Intent("look"), context, 1)


if __name__ == "__main__":
    unittest.main()
