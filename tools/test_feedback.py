import tempfile
import unittest
import io
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from agent.feedback import FeedbackLedger


def observation(x=1, y=1, direction="north", flags="00", mode="exploration"):
    game = SimpleNamespace(
        x=x, y=y, direction=direction, map_id=5, event_flags=flags,
        dungeon_flags=flags, mode=mode,
    )
    return SimpleNamespace(game=game)


class FeedbackLedgerTests(unittest.TestCase):
    def test_rewards_progress_and_penalizes_block(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = FeedbackLedger(Path(root) / "feedback.json")
            good = ledger.record("move", observation(), observation(x=3))
            bad = ledger.record(
                "move", observation(x=3), observation(x=3),
                navigation_event={"outcome": "blocked_now"},
            )
            self.assertGreater(good["delta"], 0)
            self.assertLess(bad["delta"], 0)
            self.assertIn("Correction needed", bad["feedback"])

    def test_visual_change_ratio_detects_scene_effect(self):
        def png(color):
            output = io.BytesIO()
            Image.new("RGB", (10, 10), color).save(output, format="PNG")
            return output.getvalue()
        self.assertEqual(FeedbackLedger.visual_change_ratio(png("black"), png("black")), 0)
        self.assertEqual(FeedbackLedger.visual_change_ratio(png("black"), png("white")), 1)

    def test_immediate_backtrack_is_not_globally_penalized(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = FeedbackLedger(Path(root) / "feedback.json")
            result = ledger.record(
                "move", observation(x=2), observation(x=1), immediate_backtrack=True
            )
        self.assertGreaterEqual(result["delta"], 0)
        self.assertIn("backtracking observed", result["feedback"])

    def test_repeated_local_edge_becomes_stagnation_feedback(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = FeedbackLedger(Path(root) / "feedback.json")
            first = ledger.record("move", observation(x=1), observation(x=2))
            reverse = ledger.record(
                "move", observation(x=2), observation(x=1), immediate_backtrack=True
            )
            third = ledger.record("move", observation(x=1), observation(x=2))
            fourth = ledger.record("move", observation(x=2), observation(x=1))
        self.assertGreater(first["delta"], 0)
        self.assertEqual(0, reverse["delta"])
        self.assertEqual(-2, third["delta"])
        self.assertLess(fourth["delta"], third["delta"])
        self.assertIn("test an untried local edge or direction", third["feedback"])

    def test_different_successful_edge_resets_local_oscillation_count(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = FeedbackLedger(Path(root) / "feedback.json")
            ledger.record("move", observation(x=1, y=1), observation(x=2, y=1))
            ledger.record("move", observation(x=2, y=1), observation(x=1, y=1))
            result = ledger.record("move", observation(x=1, y=1), observation(x=1, y=2))
        self.assertGreater(result["delta"], 0)
        self.assertNotIn("local_edge_traversal_count", result)

    def test_active_landmark_distance_controls_movement_reward(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = FeedbackLedger(Path(root) / "feedback.json")
            away = ledger.record(
                "move", observation(x=28, y=29), observation(x=28, y=30),
                objective_target=[28, 24],
            )
            toward = ledger.record(
                "move", observation(x=28, y=29), observation(x=28, y=28),
                objective_target=[28, 24],
            )
        self.assertGreaterEqual(away["delta"], 0)
        self.assertIn("valid detour or backtrack", away["feedback"])
        self.assertGreater(toward["delta"], 0)
        self.assertIn("distance to active landmark decreased", toward["feedback"])

    def test_move_does_not_receive_puzzle_credit_from_scrolling_map_buffer(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = FeedbackLedger(Path(root) / "feedback.json")
            result = ledger.record(
                "move",
                observation(x=4, y=20),
                observation(x=4, y=21),
                objective_target=[8, 21],
                map_tile_change_count=2,
            )
        self.assertEqual(2, result["delta"])
        self.assertNotIn("registered map buffer changed", result["feedback"])

    def test_actor_repositioning_in_movable_puzzle_is_neutral(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = FeedbackLedger(Path(root) / "feedback.json")
            result = ledger.record(
                "move",
                observation(x=7, y=21),
                observation(x=7, y=20),
                suppress_generic_movement_reward=True,
            )
        self.assertEqual(0, result["delta"])
        self.assertIn("only object-state progress earns credit", result["feedback"])

    def test_interact_that_only_repositions_actor_in_movable_puzzle_is_neutral(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = FeedbackLedger(Path(root) / "feedback.json")
            result = ledger.record(
                "interact",
                observation(x=5, y=21),
                observation(x=5, y=20),
                suppress_generic_movement_reward=True,
                map_tile_change_count=0,
            )
        self.assertEqual(0, result["delta"])
        self.assertIn("only object-state progress earns credit", result["feedback"])

    def test_legacy_move_scroll_credit_is_migrated_on_load(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "feedback.json"
            path.write_text(json.dumps({
                "schema": 1,
                "score": 8,
                "entries": [{
                    "kind": "move",
                    "delta": 8,
                    "score_after": 8,
                    "feedback": (
                        "Strong success: distance to active landmark decreased by 1 tile(s); "
                        "registered map buffer changed at 2 non-actor tile(s)"
                    ),
                    "map_tile_change_count": 2,
                }],
            }), encoding="utf-8")
            ledger = FeedbackLedger(path)
        entry = ledger.state["entries"][0]
        self.assertEqual(2, entry["delta"])
        self.assertEqual(2, ledger.state["score"])
        self.assertNotIn("registered map buffer changed", entry["feedback"])
        self.assertIn("legacy movement scroll credit removed", entry["map_tile_change_credit_policy"])

if __name__ == "__main__":
    unittest.main()
