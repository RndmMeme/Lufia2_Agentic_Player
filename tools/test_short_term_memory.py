import tempfile
import unittest
from pathlib import Path

from agent.short_term_memory import ShortTermMemory


class ShortTermMemoryTests(unittest.TestCase):
    def test_persists_context_action_and_perception_without_prompt_injection(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = ShortTermMemory(Path(directory) / "memory.json", "Reach room 4")
            memory.update_context({
                "game": {
                    "map_id": 5, "map_name": "Secret Skills Cave", "x": 21, "y": 26,
                    "direction": "west", "blocked_direction": None, "mode": "exploration",
                },
                "navigation": {
                    "current_room": {"id": "room_3", "objective": "Reach west door"},
                    "active_landmark": {
                        "id": "west_door", "live": [17, 23],
                        "effective_live": [17, 22],
                        "checkpoint": {"id": "west_door", "type": "traversal"},
                    },
                },
                "exploration_relevant_items": [{"name": "arrow", "available": True}],
                "selected_dungeon_tool": "arrow",
                "room_reset_recovery": {"eligible": False, "reason": "noise"},
            }, 4)
            memory.record_action({
                "kind": "move",
                "before": {"position": [22, 26]},
                "after": {"position": [21, 26], "blocked_direction": None},
                "requested_direction": "west",
                "requested_tiles": 1,
                "feedback": {"delta": 2, "feedback": "Good progress"},
            })
            memory.record_perception("look", "Where?", {"answer": "door"})

            recalled = memory.recall()
            self.assertEqual([21, 26], recalled["current"]["position"])
            self.assertEqual("move", recalled["recent_actions"][-1]["kind"])
            self.assertEqual([17, 22], recalled["active_target"]["effective_live"])
            self.assertEqual("traversal", recalled["active_target"]["checkpoint"]["type"])
            self.assertEqual("look", recalled["recent_perceptions"][-1]["kind"])
            self.assertEqual({"eligible": False}, recalled["room_reset_recovery"])
            self.assertTrue((Path(directory) / "memory.json").exists())
            self.assertNotIn("recent_actions", memory.prompt_hint())
