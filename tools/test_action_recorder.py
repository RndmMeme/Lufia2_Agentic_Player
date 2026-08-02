import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.action_recorder import ActionOutcomeRecorder


class ActionOutcomeRecorderTests(unittest.TestCase):
    @staticmethod
    def observation(x, event_flags="00", dungeon_flags="11"):
        game = SimpleNamespace(
            map_id=5,
            x=x,
            y=55,
            direction="north",
            blocked_direction=None,
            mode="exploration",
            event_flags=event_flags,
            dungeon_flags=dungeon_flags,
        )
        return SimpleNamespace(game=game)

    def test_writes_compact_hashed_state_and_tile_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "action_outcomes.jsonl"
            recorder = ActionOutcomeRecorder(path)
            recorder.record(
                "move",
                self.observation(28),
                self.observation(29),
                {"delta": 2, "score_after": 2, "feedback": "Good progress"},
                navigation_event={"outcome": "open", "direction": "east"},
                tile_diff={"available": True, "count": 0, "changes": []},
                requested_direction="east",
            )
            record = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(record["action"]["requested_direction"], "east")
        self.assertEqual(record["navigation"]["outcome"], "open")
        self.assertIn("event_flags_digest", record["before"])
        self.assertNotIn("event_flags", record["before"])
