import json
import tempfile
import unittest
from pathlib import Path

from agent.session_supervisor import (
    LongSessionSupervisor,
    classify_stop,
    state_fingerprint,
)


class SessionSupervisorTests(unittest.TestCase):
    def test_stop_classification_is_conservative(self):
        self.assertEqual("resume", classify_stop("reasoning_step_limit"))
        self.assertEqual("resume", classify_stop("time_limit"))
        self.assertEqual("complete", classify_stop("objective_complete"))
        self.assertEqual("new_episode", classify_stop("objective_map_boundary"))
        self.assertEqual("halt", classify_stop("battle_step_rejected"))
        self.assertEqual("halt", classify_stop("unknown"))
        self.assertEqual("operator_stop", classify_stop("operator_stop"))

    def test_fingerprint_tracks_verified_game_progress(self):
        first = {"state": {"map_id": 5, "x": 1, "y": 2, "mode": "exploration"}, "navigation": {"current_room": "room_1", "visited_rooms": ["room_1"]}}
        second = {"state": {"map_id": 5, "x": 1, "y": 3, "mode": "exploration"}, "navigation": {"current_room": "room_1", "visited_rooms": ["room_1"]}}
        self.assertNotEqual(state_fingerprint(first), state_fingerprint(second))

    def test_session_dir_must_remain_in_project(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "project"
            root.mkdir()
            with self.assertRaisesRegex(ValueError, "inside the project"):
                LongSessionSupervisor(root, Path(folder) / "outside", "goal", 1)

    def test_command_resumes_same_episode_with_learning_enabled(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            supervisor = LongSessionSupervisor(root, root / "session", "goal", 1)
            command = supervisor._command(resume=True)
        self.assertIn("--resume-run", command)
        self.assertIn("--enable-harness-gated", command)
        self.assertIn("--enable-battle", command)
        self.assertIn("--stop-file", command)

    def test_recovery_defaults_to_read_only_slot3_not_hard_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            supervisor = LongSessionSupervisor(root, root / "session", "goal", 1)
        self.assertEqual("slot3", supervisor.recovery_mode)

    def test_room_reset_requires_persisted_curated_ticket(self):
        with tempfile.TemporaryDirectory() as folder:
            episode = Path(folder)
            (episode / "short_term_memory.json").write_text(
                '{"room_reset_recovery":{"eligible":false}}', encoding="utf-8"
            )
            self.assertFalse(LongSessionSupervisor._room_reset_ticket(episode))
            (episode / "short_term_memory.json").write_text(
                '{"room_reset_recovery":{"eligible":true}}', encoding="utf-8"
            )
            self.assertTrue(LongSessionSupervisor._room_reset_ticket(episode))

    def test_repeated_local_edge_without_progress_triggers_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            episode = Path(folder)
            actions = []
            for index in range(8):
                source, target = ([17, 21], [17, 22]) if index % 2 == 0 else ([17, 22], [17, 21])
                actions.append({
                    "kind": "move", "from": source, "to": target,
                    "direction": "south" if index % 2 == 0 else "north",
                    "reward": -2 - index, "semantic_tile_changes": 0,
                    "completed_checkpoint": None, "completed_landmark": None,
                })
            (episode / "short_term_memory.json").write_text(
                json.dumps({"recent_actions": actions}), encoding="utf-8"
            )
            self.assertTrue(LongSessionSupervisor._movement_loop_ticket(episode))

    def test_recent_checkpoint_prevents_loop_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            episode = Path(folder)
            actions = [{
                "kind": "move", "from": [1, 1], "to": [1, 2],
                "direction": "south", "reward": -5,
                "semantic_tile_changes": 0,
                "completed_checkpoint": None, "completed_landmark": None,
            } for _ in range(8)]
            actions[-1]["completed_checkpoint"] = "door_entered"
            (episode / "short_term_memory.json").write_text(
                json.dumps({"recent_actions": actions}), encoding="utf-8"
            )
            self.assertFalse(LongSessionSupervisor._movement_loop_ticket(episode))

    def test_existing_session_rejects_changed_recovery_anchor(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            anchor = root / "slot3.mss"
            anchor.write_bytes(b"verified")
            supervisor = LongSessionSupervisor(root, root / "session", "goal", 1)
            supervisor.state.update({
                "recovery_anchor_path": str(anchor),
                "recovery_anchor_bytes": len(b"verified"),
                "recovery_anchor_sha256": "0" * 64,
            })
            with self.assertRaisesRegex(RuntimeError, "changed during"):
                supervisor._assert_recovery_anchor_unchanged()


if __name__ == "__main__":
    unittest.main()
