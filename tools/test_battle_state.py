import unittest

from agent.battle import BattlePhase, BattleState
from agent.game_state import ENEMY_BASE


def put_u16(data, offset, value):
    data[offset] = value & 0xFF
    data[offset + 1] = value >> 8


def state(token, *, input_mode=1, target_flags=0, enemy_hp=6, active_actor=0, queue_actor=0):
    data = bytearray(0x20000)
    data[0x09AA] = 1
    data[0x0B4E] = token
    data[0x1F55E] = input_mode
    data[0x0027] = target_flags
    data[ENEMY_BASE + 3:ENEMY_BASE + 16] = b"Red Jelly    "
    data[ENEMY_BASE + 0x53] = 0xA4
    put_u16(data, ENEMY_BASE + 0x14, enemy_hp)
    data[0x1F44E] = active_actor
    data[0x1B8C] = queue_actor
    return BattleState.from_wram(bytes(data))


class BattleStateTests(unittest.TestCase):
    def test_unproven_menu_modes_remain_unknown_but_target_flag_is_confirmed(self):
        self.assertEqual(state(0x3A).phase, BattlePhase.UNKNOWN)
        self.assertEqual(state(0x3A, target_flags=0x80).phase, BattlePhase.TARGET_SELECTION)
        self.assertEqual(state(0x3A, target_flags=0x01).phase, BattlePhase.TARGET_SELECTION)

    def test_input_mode_does_not_guess_group_or_action_cross(self):
        self.assertEqual(state(0x3A, input_mode=0).phase, BattlePhase.UNKNOWN)

    def test_execution_requires_active_actor_in_queue(self):
        self.assertEqual(
            state(0x3A, active_actor=0x04, queue_actor=0x04).phase,
            BattlePhase.EXECUTION,
        )

    def test_results_override_stale_active_action(self):
        first_page = state(0x04, enemy_hp=0, active_actor=0x04, queue_actor=0x04)
        self.assertEqual(first_page.phase, BattlePhase.RESULTS)
        result = state(0x29, enemy_hp=0, active_actor=0x04, queue_actor=0x04)
        self.assertEqual(result.phase, BattlePhase.RESULTS)
        self.assertEqual(
            state(0x2B, enemy_hp=0, active_actor=0x04, queue_actor=0x04).phase,
            BattlePhase.RESULTS,
        )


if __name__ == "__main__":
    unittest.main()
