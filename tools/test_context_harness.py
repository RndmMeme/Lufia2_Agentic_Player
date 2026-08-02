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


if __name__ == "__main__":
    unittest.main()
