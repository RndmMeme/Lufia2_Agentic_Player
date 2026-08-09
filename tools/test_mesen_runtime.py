import tempfile
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

from agent.game_state import (
    CHARACTER_BASE, CHARACTER_STRIDE, ENEMY_BASE, GameState, InventoryItem
)
from agent.intent import Intent, gate_intent
from agent.knowledge import KnowledgeRetriever
from agent.mesen_controller import MesenController


def put_u16(data, offset, value):
    data[offset] = value & 0xFF
    data[offset + 1] = value >> 8


class GameStateTests(unittest.TestCase):
    def test_decodes_confirmed_party_enemy_and_navigation_offsets(self):
        data = bytearray(0x20000)
        data[0x05AC] = 5
        data[0x05AE] = 0
        data[0x06BA] = 28
        data[0x06E2] = 32
        data[0x0692] = 4
        data[0x1272] = 2
        data[0x09A7] = 0x11
        data[0x09A9] = 1
        data[0x09AA] = 1
        data[0x091E:0x0921] = bytes.fromhex("02 00 00")
        data[0x0A7B:0x0A7F] = bytes((2, 3, 1, 4))
        data[0x0A8D:0x0A8F] = bytes((0xA8, 0x03))
        base = CHARACTER_BASE + 2 * CHARACTER_STRIDE
        data[base + 0x11] = 99
        put_u16(data, base + 0x14, 600)
        put_u16(data, base + 0x28, 700)
        enemy = ENEMY_BASE
        data[enemy + 0x03:enemy + 0x10] = b"Red Jelly    "
        data[enemy + 0x53] = 0x16
        put_u16(data, enemy + 0x14, 123)
        put_u16(data, enemy + 0x28, 200)
        state = GameState.from_wram(bytes(data))
        self.assertEqual(state.map_name, "Secret Skills Cave")
        self.assertEqual((state.x, state.y, state.direction), (28, 32, "north"))
        self.assertEqual(state.blocked_direction, "west")
        self.assertEqual(state.party[0].name, "Guy")
        self.assertEqual(state.party[0].hp, 600)
        self.assertEqual(state.enemies[0].identity, 0x16)
        self.assertEqual(state.enemies[0].name, "Red Jelly")
        self.assertEqual(state.inventory[0].name, "Bomb")
        self.assertEqual(state.inventory[0].quantity, 1)
        self.assertIn("Basement", state.progression_flags)

        with_equipment_noise = replace(
            state,
            inventory=state.inventory + (
                InventoryItem(1, 999, "equipment", "Buster Sword", 1),
            ),
        ).compact()
        self.assertIn("Basement key", with_equipment_noise["progression_items"])
        self.assertNotIn("Buster Sword", with_equipment_noise["progression_items"])

    def test_stale_enemy_structs_are_hidden_outside_battle(self):
        data = bytearray(0x20000)
        data[ENEMY_BASE + 0x03:ENEMY_BASE + 0x10] = b"Old Enemy    "
        data[ENEMY_BASE + 0x53] = 0x54
        put_u16(data, ENEMY_BASE + 0x14, 637)
        self.assertEqual(GameState.from_wram(bytes(data)).enemies, ())

    def test_overworld_mode_zero_is_still_exploration(self):
        data = bytearray(0x20000)
        data[0x05AC] = 0
        data[0x09A9] = 0
        self.assertEqual(GameState.from_wram(bytes(data)).mode, "exploration")


class IntentTests(unittest.TestCase):
    def test_rejects_unbounded_or_out_of_state_actions(self):
        with self.assertRaises(ValueError):
            Intent.from_dict({"kind": "move", "direction": "north", "count": 99})
        intent = Intent.from_dict({"kind": "battle_attack"})
        with self.assertRaises(ValueError):
            gate_intent(intent, "exploration")
        gate_intent(intent, "battle")

    def test_room_reset_is_exploration_only(self):
        intent = Intent.from_dict({"kind": "reset_room"})
        gate_intent(intent, "exploration")
        with self.assertRaises(ValueError):
            gate_intent(intent, "battle")

    def test_exploration_tool_and_facing_intents_are_typed(self):
        tool = Intent.from_dict({"kind": "select_tool", "tool": "Fire Arrow"})
        self.assertEqual(tool.tool, "fire_arrow")
        face = Intent.from_dict({"kind": "face", "direction": "east", "count": 99})
        self.assertEqual((face.direction, face.count), ("east", 1))
        gate_intent(tool, "exploration")
        gate_intent(face, "exploration")
        with self.assertRaises(ValueError):
            Intent.from_dict({"kind": "select_tool", "tool": "imaginary"})

    def test_interact_accepts_optional_cardinal_direction(self):
        directed = Intent.from_dict({"kind": "interact", "direction": "south"})
        plain = Intent.from_dict({"kind": "interact", "direction": None})
        self.assertEqual("south", directed.direction)
        self.assertIsNone(plain.direction)
        with self.assertRaises(ValueError):
            Intent.from_dict({"kind": "interact", "direction": "diagonal"})

    def test_json_null_optional_fields_remain_none(self):
        intent = Intent.from_dict({
            "kind": "move", "direction": "north", "count": 1,
            "question": None, "query": None, "tool": None,
        })
        self.assertIsNone(intent.question)
        self.assertIsNone(intent.query)
        self.assertIsNone(intent.tool)


class ControllerMovementTests(unittest.TestCase):
    def test_directed_interact_holds_a_before_direction_impulse(self):
        controller = object.__new__(MesenController)
        calls = []
        controller.chord = lambda held, pressed: calls.append((held, pressed)) or "stable"

        self.assertEqual("stable", controller.interact("north"))
        self.assertEqual([("a", "up")], calls)

    def test_tile_distance_controls_humanoid_hold_frames(self):
        calls = []

        class Bridge:
            def pulse(self, button, frames, settle_seconds):
                calls.append((button, frames, settle_seconds))

        controller = object.__new__(MesenController)
        controller.config = {
            "exploration_hold_frames": 12,
            "exploration_frames_per_tile": 6,
            "settle_seconds": 0.32,
        }
        controller.bridge = Bridge()
        controller.observe_stable = lambda: "stable"

        self.assertEqual(controller.move("north", tiles=1), "stable")
        self.assertEqual(controller.move("east", tiles=2), "stable")
        self.assertEqual(calls, [("up", 6, 0.32), ("right", 12, 0.32)])

    def test_tile_distance_never_exceeds_bridge_frame_limit(self):
        controller = object.__new__(MesenController)
        controller.config = {
            "exploration_frames_per_tile": 6,
            "settle_seconds": 0.32,
        }
        controller.bridge = object()
        with self.assertRaisesRegex(ValueError, "between 1 and 5"):
            controller.move("south", tiles=6)

    @staticmethod
    def _field_observation(mode=1, map_id=5, in_battle=False):
        game = SimpleNamespace(
            exploration_mode=mode,
            map_id=map_id,
            in_battle=in_battle,
        )
        return SimpleNamespace(game=game)

    @patch("agent.mesen_controller.time.sleep", return_value=None)
    def test_room_reset_uses_humanoid_select_up_confirm_sequence(self, _sleep):
        calls = []

        class Bridge:
            def pulse(self, button, frames, settle_seconds):
                calls.append((button, frames, settle_seconds))

        controller = object.__new__(MesenController)
        controller.config = {
            "reset_confirmation_presses": 2,
            "reset_menu_open_seconds": 0,
            "reset_selection_seconds": 0,
            "reset_confirmation_seconds": 0,
        }
        controller.bridge = Bridge()
        observations = iter([
            self._field_observation(),
            self._field_observation(mode=4),
            self._field_observation(mode=5),
            self._field_observation(),
        ])
        controller.observe_stable = lambda timeout=2.0: next(observations)

        before, after = controller.reset_room()

        self.assertEqual(before.game.exploration_mode, 1)
        self.assertEqual(after.game.exploration_mode, 1)
        self.assertEqual([call[0] for call in calls], ["select", "up", "a"])

    @patch("agent.mesen_controller.time.sleep", return_value=None)
    def test_room_reset_rejects_unconfirmed_menu_without_pressing_a(self, _sleep):
        calls = []

        class Bridge:
            def pulse(self, button, frames, settle_seconds):
                calls.append(button)

        controller = object.__new__(MesenController)
        controller.config = {"reset_menu_open_seconds": 0}
        controller.bridge = Bridge()
        observations = iter([
            self._field_observation(),
            self._field_observation(mode=2),
        ])
        controller.observe_stable = lambda timeout=2.0: next(observations)

        with self.assertRaisesRegex(RuntimeError, "menu was not confirmed"):
            controller.reset_room()
        self.assertEqual(calls, ["select", "select"])


class KnowledgeTests(unittest.TestCase):
    def test_keyword_retrieval_is_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "guide.txt"
            source.write_text("Secret cave lever bridge.\n\nUnrelated town shop.", encoding="utf-8")
            retriever = KnowledgeRetriever({"max_snippets": 1, "max_chars_per_snippet": 20}, [source])
            hits = retriever.search("secret lever")
            self.assertEqual(len(hits), 1)
            self.assertLessEqual(len(hits[0]["text"]), 20)


if __name__ == "__main__":
    unittest.main()
