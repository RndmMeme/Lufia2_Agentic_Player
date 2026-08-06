import tempfile
import unittest
import io
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

if __name__ == "__main__":
    unittest.main()
