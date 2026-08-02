import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.battle import BattleCoordinator, BattleDecision, BattleInputStage
from agent.game_state import GameState


CAPTURES = (
    Path(__file__).resolve().parents[1]
    / "legacy/wram_research/mesen_validation/gameplay"
)


def observation(name: str):
    data = (CAPTURES / name).read_bytes()
    return SimpleNamespace(wram=data, game=GameState.from_wram(data))


class FakeController:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def _next(self):
        if not self.outputs:
            raise AssertionError("Unexpected controller input")
        return self.outputs.pop(0)

    def pulse(self, button):
        self.calls.append(("pulse", button))
        return self._next()

    def chord(self, held_button, pressed_button="a"):
        self.calls.append(("chord", held_button, pressed_button))
        return self._next()

    def observe_stable(self):
        self.calls.append(("observe_stable",))
        return self._next()


class QueuedDecisions:
    def __init__(self, option_ids):
        self.option_ids = list(option_ids)
        self.seen = []

    def __call__(self, state, options, advisory):
        self.seen.append((state, options, advisory))
        option_id = self.option_ids.pop(0)
        return BattleDecision(option_id, "Tactical choice", "Known bounded risk", "Reassess")


class BattleCoordinatorTests(unittest.TestCase):
    def test_llm_owns_group_and_character_command_choices(self):
        controller = FakeController([
            observation("battle_group_attack_cursor.bin"),
            observation("battle_magic_cursor_true_top.bin"),
        ])
        decisions = QueuedDecisions(["group:fight", "command:0:magic"])
        battle = BattleCoordinator(controller, decisions)
        battle.begin_new_battle()

        first = battle.step(observation("battle_group_attack_cursor.bin"))
        self.assertEqual(first.event, "group_fight")
        self.assertEqual(battle.driver.session.stage, BattleInputStage.ACTION_CROSS)

        second = battle.step(first.observation)
        self.assertEqual(second.event, "command_magic_menu")
        self.assertEqual(battle.driver.session.stage, BattleInputStage.SUBMENU)
        self.assertEqual(controller.calls, [("pulse", "a"), ("chord", "up", "a")])
        self.assertEqual(len(decisions.seen), 2)
        self.assertNotIn("inventory", decisions.seen[0][0])
        self.assertIn("party", decisions.seen[0][0])

    def test_mid_battle_unknown_stage_sends_no_input(self):
        controller = FakeController([])
        battle = BattleCoordinator(controller, QueuedDecisions([]))
        with self.assertRaisesRegex(RuntimeError, "hierarchy is unknown"):
            battle.step(observation("battle_group_attack_cursor.bin"))
        self.assertEqual(controller.calls, [])

    def test_wrong_resumed_actor_is_rejected_before_model_or_input(self):
        controller = FakeController([])
        decisions = QueuedDecisions([])
        battle = BattleCoordinator(controller, decisions)
        battle.driver.resume_at_action_cross(actor_slot=1)
        with self.assertRaisesRegex(RuntimeError, "conflicts with first uncommitted"):
            battle.step(observation("battle_group_attack_cursor.bin"))
        self.assertEqual(controller.calls, [])
        self.assertEqual(decisions.seen, [])


if __name__ == "__main__":
    unittest.main()
