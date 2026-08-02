"""Verified three-stage battle input: action chord, list choice, target."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agent.battle.menu import BattleMenuReader, BattleMenuType
from agent.battle.policy import BattleOption
from agent.battle.state import BattleState
from agent.mesen_controller import MesenController, Observation


COMMAND_DIRECTIONS = {
    "magic_menu": "up",
    "ip_menu": "down",
    "item_menu": "left",
    "defend": "right",
}


class BattleInputError(RuntimeError):
    pass


class BattleInputStage(str, Enum):
    """Hierarchical UI state known from actions taken by this driver."""

    PRE_MENU = "pre_menu"
    ACTION_CROSS = "action_cross"
    SUBMENU = "submenu"
    TARGET = "target"
    EXECUTION = "execution"
    RESULTS = "results"
    UNKNOWN = "unknown"


@dataclass
class BattleInputSession:
    actor_slot: int = 0
    selected_option: BattleOption | None = None
    stage: BattleInputStage = BattleInputStage.UNKNOWN


class BattleInputDriver:
    """Drive only confirmed inputs and verify every stage before continuing."""

    def __init__(self, controller: MesenController):
        self.controller = controller
        self.session = BattleInputSession()
        self.last_input_count = 0

    def begin_at_pre_menu(self) -> None:
        """Declare the normal, freshly-entered battle pre-menu as the start."""
        self.session = BattleInputSession(stage=BattleInputStage.PRE_MENU)

    def resume_at_action_cross(self, actor_slot: int = 0) -> None:
        """Explicit recovery hook; callers must have visually/externally confirmed it."""
        self.session = BattleInputSession(
            actor_slot=actor_slot,
            stage=BattleInputStage.ACTION_CROSS,
        )

    def resume_at_results(self) -> None:
        self.session = BattleInputSession(stage=BattleInputStage.RESULTS)

    @staticmethod
    def next_uncommitted_actor(state: BattleState) -> int | None:
        for member in state.game.party:
            if member.alive and state.stored_commands[member.slot].command == 0:
                return member.slot
        return None

    def _require_stage(self, expected: BattleInputStage) -> None:
        if self.session.stage != expected:
            raise BattleInputError(
                f"Input requires {expected.value}, current stage is {self.session.stage.value}"
            )

    @staticmethod
    def state(observation: Observation) -> BattleState:
        return BattleState.from_wram(observation.wram)

    def choose_group_action(self, action: str) -> Observation:
        self._require_stage(BattleInputStage.PRE_MENU)
        self.last_input_count = 1
        if action == "fight":
            observation = self.controller.pulse("a")
            self.session = BattleInputSession(
                actor_slot=0,
                stage=BattleInputStage.ACTION_CROSS,
            )
        elif action == "flee":
            observation = self.controller.chord("down", "a")
            self.session.stage = BattleInputStage.EXECUTION
        elif action == "change_position":
            observation = self.controller.chord("up", "a")
            self.session.stage = BattleInputStage.UNKNOWN
        else:
            raise ValueError(f"Unknown group action: {action}")
        if not observation.game.in_battle:
            if action == "flee":
                return observation
            raise BattleInputError(f"{action} unexpectedly left battle")
        return observation

    def cancel_action_cross(self) -> Observation:
        """B on the neutral action cross returns to the fight/flee/change menu."""
        self._require_stage(BattleInputStage.ACTION_CROSS)
        self.last_input_count = 1
        observation = self.controller.pulse("b")
        state = self.state(observation)
        if not state.game.in_battle:
            self.session.stage = BattleInputStage.UNKNOWN
            raise BattleInputError("B unexpectedly left battle")
        # 0B4E exposes 09/0A/0B only while a pre-menu direction is held.  Its
        # idle value remained 13 in the live B transition, so it cannot verify
        # the resting pre-menu.  The known input transition is authoritative.
        self.session = BattleInputSession(stage=BattleInputStage.PRE_MENU)
        return observation

    def choose_command(self, option: BattleOption) -> Observation:
        self._require_stage(BattleInputStage.ACTION_CROSS)
        self.last_input_count = 1
        if option.actor_slot != self.session.actor_slot:
            raise BattleInputError(
                f"Expected actor slot {self.session.actor_slot}, got {option.actor_slot}"
            )
        if option.kind == "attack":
            observation = self.controller.pulse("a")
        elif option.kind in COMMAND_DIRECTIONS:
            observation = self.controller.chord(COMMAND_DIRECTIONS[option.kind], "a")
        else:
            raise BattleInputError(f"Not an action-cross option: {option.kind}")

        state = self.state(observation)
        menu = BattleMenuReader.menu_type(state, observation.wram)
        expected = {
            "attack": {BattleMenuType.TARGET},
            "magic_menu": {BattleMenuType.MAGIC},
            "item_menu": {BattleMenuType.ITEM},
            "ip_menu": {BattleMenuType.IP},
            # Defend has no list or target and may advance immediately.
            "defend": {BattleMenuType.UNKNOWN},
        }[option.kind]
        # A Lua pulse can occasionally land between the game's polling windows.
        # Retry once only while every semantic indicator proves no transition:
        # no target, no submenu prompt, and no stored command for this actor.
        stored = state.stored_commands[option.actor_slot].command
        if menu == BattleMenuType.UNKNOWN and stored == 0 and state.target_flags == 0:
            if option.kind == "attack":
                observation = self.controller.pulse("a")
            else:
                observation = self.controller.chord(COMMAND_DIRECTIONS[option.kind], "a")
            self.last_input_count += 1
            state = self.state(observation)
            menu = BattleMenuReader.menu_type(state, observation.wram)
        if menu not in expected:
            raise BattleInputError(
                f"{option.kind} reached {menu.value}, expected {sorted(item.value for item in expected)}"
            )
        if option.kind == "defend":
            command = state.stored_commands[option.actor_slot].command
            if command != 0x04:
                raise BattleInputError(f"Defend was not stored (command=0x{command:02X})")
            next_actor = self.next_uncommitted_actor(state)
            self.session.actor_slot = next_actor if next_actor is not None else len(state.game.party)
            self.session.stage = BattleInputStage.EXECUTION if next_actor is None else BattleInputStage.ACTION_CROSS
        else:
            self.session.selected_option = option
            self.session.stage = (
                BattleInputStage.TARGET
                if option.kind == "attack"
                else BattleInputStage.SUBMENU
            )
        return observation

    def choose_visible_entry(self, observation: Observation, option: BattleOption) -> Observation:
        self._require_stage(BattleInputStage.SUBMENU)
        self.last_input_count = 0
        menu = BattleMenuReader.menu_type(self.state(observation), observation.wram)
        expected = {
            "spell": BattleMenuType.MAGIC,
            "item": BattleMenuType.ITEM,
            "ip": BattleMenuType.IP,
        }.get(option.kind)
        if expected is None or menu != expected or not option.usable or option.menu_index is None:
            raise BattleInputError("Requested entry is not usable in the current confirmed submenu")

        if option.kind == "spell":
            current = observation.wram[0x0012]
            current_row, current_col = divmod(current, 2)
            target_row, target_col = divmod(option.menu_index, 2)
            observation = self._move_many(observation, "up" if target_row < current_row else "down", abs(target_row - current_row))
            observation = self._move_many(observation, "left" if target_col < current_col else "right", abs(target_col - current_col))
        elif option.kind == "item":
            current = observation.wram[0x0012]
            delta = (option.menu_index - current) // 2
            observation = self._move_many(observation, "up" if delta < 0 else "down", abs(delta))
        else:
            current = observation.wram[0x0014]
            delta = option.menu_index - current
            observation = self._move_many(observation, "up" if delta < 0 else "down", abs(delta))

        observation = self.controller.pulse("a")
        self.last_input_count += 1
        state = self.state(observation)
        if BattleMenuReader.menu_type(state, observation.wram) != BattleMenuType.TARGET:
            raise BattleInputError("List choice did not reach target selection")
        self.session.selected_option = option
        self.session.stage = BattleInputStage.TARGET
        return observation

    def cancel_submenu(self) -> Observation:
        """Return from Magic/Item/IP list to the same actor's action cross."""
        self._require_stage(BattleInputStage.SUBMENU)
        self.last_input_count = 1
        observation = self.controller.pulse("b")
        if not observation.game.in_battle:
            self.session.stage = BattleInputStage.UNKNOWN
            raise BattleInputError("B unexpectedly left battle")
        if BattleMenuReader.menu_type(self.state(observation), observation.wram) != BattleMenuType.UNKNOWN:
            self.session.stage = BattleInputStage.UNKNOWN
            raise BattleInputError("B did not leave the confirmed battle submenu")
        self.session.selected_option = None
        self.session.stage = BattleInputStage.ACTION_CROSS
        return observation

    def cancel_target(self, observation: Observation) -> Observation:
        """Back out one level from target selection without storing a command."""
        self._require_stage(BattleInputStage.TARGET)
        self.last_input_count = 1
        previous = self.session.selected_option
        observation = self.controller.pulse("b")
        if not observation.game.in_battle:
            self.session.stage = BattleInputStage.UNKNOWN
            raise BattleInputError("B unexpectedly left battle")
        menu = BattleMenuReader.menu_type(self.state(observation), observation.wram)
        if previous and previous.kind in {"spell", "item", "ip"}:
            expected = {
                "spell": BattleMenuType.MAGIC,
                "item": BattleMenuType.ITEM,
                "ip": BattleMenuType.IP,
            }[previous.kind]
            if menu != expected:
                self.session.stage = BattleInputStage.UNKNOWN
                raise BattleInputError(f"Target cancel reached {menu.value}, expected {expected.value}")
            self.session.stage = BattleInputStage.SUBMENU
        else:
            if menu != BattleMenuType.UNKNOWN:
                self.session.stage = BattleInputStage.UNKNOWN
                raise BattleInputError("Attack target cancel did not return to action cross")
            self.session.selected_option = None
            self.session.stage = BattleInputStage.ACTION_CROSS
        return observation

    def choose_target(self, observation: Observation, target_index: int, all_targets: bool = False) -> Observation:
        self._require_stage(BattleInputStage.TARGET)
        self.last_input_count = 0
        state = self.state(observation)
        if BattleMenuReader.menu_type(state, observation.wram) != BattleMenuType.TARGET:
            raise BattleInputError("Target input requested outside confirmed target selection")
        if all_targets:
            observation = self.controller.pulse("r")
            self.last_input_count += 1
        else:
            delta = int(target_index) - state.target_index
            observation = self._move_many(observation, "left" if delta < 0 else "right", abs(delta))
        observation = self.controller.pulse("a")
        self.last_input_count += 1
        after = self.state(observation)
        stored = after.stored_commands[self.session.actor_slot]
        if not stored.command or not stored.target_mask:
            raise BattleInputError("Target confirmation did not store command and target mask")
        next_actor = self.next_uncommitted_actor(after)
        self.session.actor_slot = next_actor if next_actor is not None else len(after.game.party)
        self.session.selected_option = None
        self.session.stage = BattleInputStage.EXECUTION if next_actor is None else BattleInputStage.ACTION_CROSS
        return observation

    def _move_many(self, observation: Observation, direction: str, count: int) -> Observation:
        for _ in range(count):
            observation = self.controller.pulse(direction)
            self.last_input_count += 1
        return observation
