import tempfile
import json
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

    def test_recall_retains_six_perceptions_for_internal_evidence_correlation(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = ShortTermMemory(Path(directory) / "memory.json", "Solve room")
            for index in range(7):
                memory.record_perception("look", str(index), {"index": index}, index)
            recalled = memory.recall()["recent_perceptions"]
            self.assertEqual(6, len(recalled))
            self.assertEqual(1, recalled[0]["result"]["index"])

    def test_room_reset_is_hard_cognitive_episode_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = ShortTermMemory(Path(directory) / "memory.json", "Solve room")
            memory.record_perception("look", "Where?", {"answer": "wall"}, 3)
            memory.record_action({
                "kind": "interact",
                "before": {"position": [8, 20]},
                "after": {"position": [9, 20]},
                "requested_direction": "east",
                "map_tile_change_count": 2,
                "feedback": {},
            })
            memory.record_action({
                "kind": "reset_room",
                "before": {"position": [9, 20]},
                "after": {"position": [14, 23]},
                "map_tile_change_count": 20,
                "feedback": {},
            })
            recalled = memory.recall()
            self.assertEqual([], recalled["recent_perceptions"])
            self.assertEqual([], recalled["confirmed_world_changes"])
            self.assertEqual(["reset_room"], [a["kind"] for a in recalled["recent_actions"]])
            self.assertIsNone(recalled["active_target"])
            self.assertEqual([14, 23], recalled["current"]["position"])
            self.assertEqual("reset_room", recalled["room_episode"]["origin"])
            self.assertEqual("unsolved", recalled["room_episode"]["puzzle_status"])
            self.assertEqual(
                "fresh_observation_required",
                recalled["room_episode"]["perception_status"],
            )

            memory.record_perception("look", "Fresh room?", {"answer": "pillar"}, 4)
            recalled = memory.recall()
            self.assertEqual(1, len(recalled["recent_perceptions"]))
            self.assertEqual(
                "observed_after_reset",
                recalled["room_episode"]["perception_status"],
            )

            memory.record_action({
                "kind": "move",
                "before": {"position": [14, 23]},
                "after": {"position": [14, 22]},
                "requested_direction": "north",
                "feedback": {},
            })
            self.assertEqual(
                "reformed_from_post_reset_live_state",
                memory.recall()["room_episode"]["intent_status"],
            )

    def test_confirmed_map_change_persists_until_room_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = ShortTermMemory(Path(directory) / "memory.json", "Solve room")
            base = {
                "game": {"map_id": 5, "map_name": "Cave", "x": 8, "y": 21},
                "navigation": {"current_room": {"id": "room_4"}},
            }
            memory.update_context(base, 1)
            memory.record_action({
                "kind": "interact",
                "before": {"position": [8, 21]},
                "after": {"position": [8, 20], "blocked_direction": None},
                "requested_direction": "north",
                "map_tile_change_count": 2,
                "map_tile_changes": [{"live": [8, 18]}, {"live": [8, 19]}],
                "feedback": {"delta": 8, "feedback": "Strong success"},
            })
            memory.update_context(base, 2)
            change = memory.recall()["confirmed_world_changes"][0]
            self.assertEqual([[8, 18], [8, 19]], change["changed_live_tiles"])
            self.assertIn("interact north", change["effect"]["message"])
            self.assertEqual([8, 19], change["movable_object_after"])
            self.assertEqual([8, 20], change["actor_after"])

            changed_room = {
                **base,
                "navigation": {"current_room": {"id": "room_5"}},
            }
            memory.update_context(changed_room, 3)
            self.assertEqual([], memory.recall()["confirmed_world_changes"])

    def test_live_move_buffer_diff_is_not_remembered_as_world_change(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = ShortTermMemory(Path(directory) / "memory.json", "Solve room")
            memory.record_action({
                "kind": "move",
                "before": {"position": [4, 20]},
                "after": {"position": [4, 21]},
                "requested_direction": "south",
                "map_tile_change_count": 2,
                "map_tile_changes": [{"live": [1, 1]}, {"live": [1, 2]}],
                "feedback": {},
            })
            self.assertEqual([], memory.recall()["confirmed_world_changes"])

    def test_legacy_live_move_world_changes_are_removed_on_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            memory = ShortTermMemory(path, "Solve room")
            memory.state["confirmed_world_changes"] = [{
                "source_landmark": "observed_world_change",
                "action_kind": "move",
                "effect": {"message": "scroll noise"},
            }]
            memory._save()
            loaded = ShortTermMemory(path, "Solve room")
            self.assertEqual([], loaded.recall()["confirmed_world_changes"])

    def test_recovery_ignores_map_buffer_replacement_on_room_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = [
                {
                    "action": {
                        "kind": "move", "requested_direction": "south",
                        "map_tile_change_count": 2,
                        "map_tile_changes": [{"live": [14, 21]}],
                    },
                    "before": {"position": [14, 19]},
                    "after": {"position": [14, 20]},
                    "navigation": {"new_room": True},
                },
                {
                    "action": {
                        "kind": "interact", "requested_direction": "north",
                        "map_tile_change_count": 2,
                        "map_tile_changes": [{"live": [8, 18]}],
                    },
                    "before": {"position": [8, 21]},
                    "after": {"position": [8, 20]},
                    "navigation": {"new_room": False},
                },
            ]
            (root / "action_outcomes.jsonl").write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )
            memory = ShortTermMemory(root / "memory.json", "Solve room")
            changes = memory.recall()["confirmed_world_changes"]
            self.assertEqual(1, len(changes))
            self.assertIn("interact north", changes[0]["effect"]["message"])
