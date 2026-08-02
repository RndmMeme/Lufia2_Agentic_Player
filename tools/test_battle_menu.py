import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.battle import (
    BattleInputDriver,
    BattleInputError,
    BattleInputStage,
    BattleMenuReader,
    BattleMenuType,
    BattleOption,
    BattleState,
)
from agent.game_state import GameState


CAPTURES = (
    Path(__file__).resolve().parents[1]
    / "legacy/wram_research/mesen_validation/gameplay"
)


def capture(name: str) -> bytes:
    data = (CAPTURES / name).read_bytes()
    if len(data) != 0x20000:
        raise AssertionError(f"Invalid capture length: {name}")
    return data


def observation(name: str):
    data = capture(name)
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


class BattleMenuCaptureTests(unittest.TestCase):
    def test_confirmed_capture_types(self):
        expected = {
            "battle_group_attack_cursor.bin": BattleMenuType.UNKNOWN,
            "battle_magic_cursor_true_top.bin": BattleMenuType.MAGIC,
            "battle_item_cursor_1.bin": BattleMenuType.ITEM,
            "battle_ip_cursor_1_zirco_ax.bin": BattleMenuType.IP,
            "battle_target_enemy_1.bin": BattleMenuType.TARGET,
        }
        for name, menu_type in expected.items():
            with self.subTest(name=name):
                data = capture(name)
                self.assertEqual(
                    BattleMenuReader.menu_type(BattleState.from_wram(data), data),
                    menu_type,
                )

    def test_magic_capture_exposes_live_randomized_cost_and_availability(self):
        data = capture("battle_magic_cursor_true_top.bin")
        options = BattleMenuReader.visible_magic(data, actor_slot=0, actor_identity=2)
        by_name = {option.name: option for option in options}
        self.assertFalse(by_name["Reset"].usable)
        self.assertEqual(by_name["Fireball"].mp_cost, 6)
        self.assertEqual(by_name["Fireball"].menu_index, 10)

    def test_item_capture_preserves_empty_storage_slots(self):
        data = capture("battle_item_cursor_1.bin")
        options = BattleMenuReader.visible_items(data, actor_slot=0)
        by_name = {option.name: option for option in options}
        self.assertEqual(by_name["Charred newt"].storage_slot, 1)
        self.assertEqual(by_name["Charred newt"].menu_index, 2)
        self.assertFalse(by_name["Curselifter"].usable)

    def test_ip_capture_uses_rendered_skill_and_equipment_id(self):
        data = capture("battle_ip_cursor_1_zirco_ax.bin")
        options = BattleMenuReader.visible_ip(data, actor_slot=0)
        sleep_stinger = next(option for option in options if option.name == "Sleep stinger")
        self.assertEqual(sleep_stinger.menu_index, 2)
        self.assertEqual(sleep_stinger.ip_cost, 96)
        self.assertTrue(sleep_stinger.usable)
        self.assertEqual(sleep_stinger.ability_id, 0x00F9)


class BattleInputDriverTests(unittest.TestCase):
    def test_fight_then_b_returns_to_pre_menu(self):
        controller = FakeController([
            # This capture visibly shows the cursorless action cross for Artea;
            # the stored Guy command is irrelevant to the transition test.
            observation("battle_guy_defend.bin"),
            observation("battle_group_attack_cursor.bin"),
        ])
        driver = BattleInputDriver(controller)
        driver.begin_at_pre_menu()
        driver.choose_group_action("fight")
        self.assertEqual(driver.session.stage, BattleInputStage.ACTION_CROSS)
        driver.cancel_action_cross()
        self.assertEqual(driver.session.stage, BattleInputStage.PRE_MENU)
        self.assertEqual(controller.calls, [("pulse", "a"), ("pulse", "b")])

    def test_action_cross_uses_only_confirmed_chord_for_magic(self):
        controller = FakeController([observation("battle_magic_cursor_true_top.bin")])
        driver = BattleInputDriver(controller)
        driver.resume_at_action_cross(actor_slot=0)
        option = BattleOption("magic_menu", 0, "Magic", 0)
        driver.choose_command(option)
        self.assertEqual(controller.calls, [("chord", "up", "a")])
        self.assertEqual(driver.session.stage, BattleInputStage.SUBMENU)

    def test_attack_is_plain_a_and_reaches_target(self):
        controller = FakeController([observation("battle_target_enemy_1.bin")])
        driver = BattleInputDriver(controller)
        driver.resume_at_action_cross(actor_slot=0)
        driver.choose_command(BattleOption("attack", 0, "Attack", 0))
        self.assertEqual(controller.calls, [("pulse", "a")])
        self.assertEqual(driver.session.stage, BattleInputStage.TARGET)

    def test_lost_attack_pulse_retries_once_only_after_proven_no_transition(self):
        controller = FakeController([
            observation("battle_group_attack_cursor.bin"),
            observation("battle_target_enemy_1.bin"),
        ])
        driver = BattleInputDriver(controller)
        driver.resume_at_action_cross(actor_slot=0)
        driver.choose_command(BattleOption("attack", 0, "Attack", 0))
        self.assertEqual(controller.calls, [("pulse", "a"), ("pulse", "a")])
        self.assertEqual(driver.last_input_count, 2)
        self.assertEqual(driver.session.stage, BattleInputStage.TARGET)

    def test_unknown_stage_fails_before_sending_input(self):
        controller = FakeController([])
        driver = BattleInputDriver(controller)
        with self.assertRaises(BattleInputError):
            driver.choose_command(BattleOption("attack", 0, "Attack", 0))
        self.assertEqual(controller.calls, [])


if __name__ == "__main__":
    unittest.main()
