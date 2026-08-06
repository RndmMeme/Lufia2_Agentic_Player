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
