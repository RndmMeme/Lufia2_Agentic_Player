"""LLM-owned battle coordinator over verified, hierarchical input primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agent.battle.decision import BattleDecision
from agent.battle.driver import BattleInputDriver, BattleInputStage
from agent.battle.menu import BattleMenuReader, BattleMenuType
from agent.battle.policy import BattleOption, BattlePolicy, CombatMemory
from agent.battle.state import BattlePhase, BattleState
from agent.mesen_controller import MesenController, Observation


DecisionFunction = Callable[[dict, list[BattleOption], dict], BattleDecision]


@dataclass(frozen=True)
class BattleStepResult:
    observation: Observation
    event: str
    inputs: int
    decision: BattleDecision | None = None


class BattleCoordinator:
    """Advance one battle UI decision or one non-tactical wait at a time."""

    def __init__(self, controller: MesenController, decide: DecisionFunction):
        self.controller = controller
        self.decide = decide
        self.driver = BattleInputDriver(controller)
        self.policy = BattlePolicy()
        self.memory = CombatMemory()

    def begin_new_battle(self) -> None:
        # Ordinary encounters start on the fight/flee/change-position pre-menu.
        self.driver.begin_at_pre_menu()

    @staticmethod
    def _state_payload(state: BattleState, stage: BattleInputStage) -> dict:
        def combatant(member) -> dict:
            return {
                "slot": member.slot,
                "name": member.name,
                "identity": member.identity,
                "level": member.level,
                "status": member.status,
                "hp": member.hp,
                "max_hp": member.max_hp,
                "mp": member.mp,
                "max_mp": member.max_mp,
                "ip": member.ip,
                "attack": member.attack,
                "defense": member.defense,
                "agility": member.agility,
                "intelligence": member.intelligence,
                "magic_resistance": member.magic_resistance,
            }

        return {
            "ui_stage": stage.value,
            "party": [combatant(member) for member in state.game.party],
            "enemies": [combatant(member) for member in state.game.enemies],
            "stored_commands": [
                {
                    "party_slot": command.party_slot,
                    "target_mask": command.target_mask,
                    "command": command.command,
                    "ability_data": list(command.ability_data),
                    "actor_mask": command.actor_mask,
                }
                for command in state.stored_commands
            ],
            "target_index": state.target_index,
            "target_flags": state.target_flags,
            "initiative": [
                {"actor_mask": entry.actor_mask, "initiative": entry.initiative}
                for entry in state.initiative
            ] if state.phase == BattlePhase.EXECUTION else [],
            "initiative_authoritative": state.phase == BattlePhase.EXECUTION,
        }

    def _choose(self, state: BattleState, options: list[BattleOption]) -> tuple[BattleOption, BattleDecision]:
        usable = [option for option in options if option.usable]
        if not usable:
            raise RuntimeError(f"No legal option at battle stage {self.driver.session.stage.value}")
        decision = self.decide(
            self._state_payload(state, self.driver.session.stage),
            usable,
            self.policy.situation(state, self.memory),
        )
        selected = next(
            (option for option in usable if option.resolved_id == decision.option_id),
            None,
        )
        if selected is None:
            raise RuntimeError("Validated battle decision was not found in legal options")
        return selected, decision

    @staticmethod
    def _back_option(actor_slot: int, origin: str) -> BattleOption:
        return BattleOption(
            "back",
            actor_slot,
            "Back without committing",
            0,
            option_id=f"back:{actor_slot}:{origin}",
        )

    @staticmethod
    def _entry_input_count(data: bytes, option: BattleOption) -> int:
        if option.menu_index is None:
            return 1
        if option.kind == "spell":
            current_row, current_col = divmod(data[0x0012], 2)
            target_row, target_col = divmod(option.menu_index, 2)
            return abs(target_row - current_row) + abs(target_col - current_col) + 1
        if option.kind == "item":
            return abs(option.menu_index - data[0x0012]) // 2 + 1
        return abs(option.menu_index - data[0x0014]) + 1

    def _submenu_options(self, state: BattleState, data: bytes) -> list[BattleOption]:
        actor = self.driver.session.actor_slot
        menu = BattleMenuReader.menu_type(state, data)
        if menu == BattleMenuType.MAGIC:
            identity = state.game.party[actor].identity
            options = BattleMenuReader.visible_magic(data, actor, identity)
        elif menu == BattleMenuType.ITEM:
            options = BattleMenuReader.visible_items(data, actor)
        elif menu == BattleMenuType.IP:
            options = BattleMenuReader.visible_ip(data, actor)
        else:
            raise RuntimeError(f"Battle submenu stage has no confirmed prompt: {menu.value}")
        return [*options, self._back_option(actor, menu.value)]

    def _target_options(self, state: BattleState) -> list[BattleOption]:
        base = self.driver.session.selected_option
        if base is None:
            raise RuntimeError("Target stage has no selected battle action")
        enemy_side = bool(state.target_flags & 0x80)
        combatants = state.game.enemies if enemy_side else state.game.party
        candidates = [
            member for member in combatants
            if member.alive or (not enemy_side and base.revives)
        ]
        prefix = 0x80 if enemy_side else 0
        options = [
            BattleOption(
                "target",
                base.actor_slot,
                f"{base.name} -> {member.name} (slot {member.slot + 1})",
                prefix | (1 << member.slot),
                option_id=f"{base.resolved_id}:target:{prefix | (1 << member.slot):02X}",
                menu_index=member.slot,
                ability_id=base.ability_id,
                description=base.description,
                target_side="enemy" if enemy_side else "ally",
            )
            for member in candidates
        ]
        if base.supports_group_toggle and candidates:
            mask = prefix | sum(1 << member.slot for member in candidates)
            options.append(BattleOption(
                "target",
                base.actor_slot,
                f"{base.name} -> all {'enemies' if enemy_side else 'allies'}",
                mask,
                all_targets=True,
                option_id=f"{base.resolved_id}:target:all:{mask:02X}",
                menu_index=state.target_index,
                ability_id=base.ability_id,
                description=base.description,
                target_side="enemy" if enemy_side else "ally",
            ))
        options.append(self._back_option(base.actor_slot, "target"))
        return options

    def step(self, observation: Observation) -> BattleStepResult:
        self.driver.last_input_count = 0
        state = BattleState.from_wram(observation.wram)
        stage = self.driver.session.stage
        if not state.game.in_battle:
            self.driver.session.stage = BattleInputStage.UNKNOWN
            return BattleStepResult(observation, "battle_ended", 0)

        # These phases have independent confirmed WRAM evidence and therefore
        # override a predicted UI stage after animations or a resumed run.
        if state.phase == BattlePhase.RESULTS:
            self.driver.session.stage = BattleInputStage.RESULTS
            stage = BattleInputStage.RESULTS
        elif state.phase == BattlePhase.EXECUTION:
            self.driver.session.stage = BattleInputStage.EXECUTION
            stage = BattleInputStage.EXECUTION

        if stage == BattleInputStage.PRE_MENU:
            options = [
                BattleOption("fight", -1, "Fight", 0, option_id="group:fight"),
                BattleOption("flee", -1, "Flee", 0, option_id="group:flee"),
            ]
            option, decision = self._choose(state, options)
            after = self.driver.choose_group_action(option.kind)
            return BattleStepResult(
                after, f"group_{option.kind}", self.driver.last_input_count, decision
            )

        if stage == BattleInputStage.ACTION_CROSS:
            actor = self.driver.session.actor_slot
            inferred = self.driver.next_uncommitted_actor(state)
            if inferred != actor:
                raise RuntimeError(
                    f"Declared action-cross actor {actor} conflicts with first "
                    f"uncommitted living command slot {inferred}; no input sent"
                )
            options = BattleMenuReader.command_options(state, observation.wram, actor)
            option, decision = self._choose(state, options)
            after = self.driver.choose_command(option)
            return BattleStepResult(
                after, f"command_{option.kind}", self.driver.last_input_count, decision
            )

        if stage == BattleInputStage.SUBMENU:
            options = self._submenu_options(state, observation.wram)
            option, decision = self._choose(state, options)
            if option.kind == "back":
                after = self.driver.cancel_submenu()
                return BattleStepResult(after, "submenu_back", 1, decision)
            count = self._entry_input_count(observation.wram, option)
            after = self.driver.choose_visible_entry(observation, option)
            return BattleStepResult(after, f"select_{option.kind}", count, decision)

        if stage == BattleInputStage.TARGET:
            options = self._target_options(state)
            option, decision = self._choose(state, options)
            if option.kind == "back":
                after = self.driver.cancel_target(observation)
                return BattleStepResult(after, "target_back", 1, decision)
            moves = abs((option.menu_index or 0) - state.target_index)
            after = self.driver.choose_target(
                observation,
                option.menu_index or 0,
                all_targets=option.all_targets,
            )
            return BattleStepResult(
                after,
                "target_confirmed",
                moves + 1 + int(option.all_targets),
                decision,
            )

        if stage == BattleInputStage.EXECUTION:
            if state.phase == BattlePhase.RESULTS:
                self.driver.session.stage = BattleInputStage.RESULTS
                return BattleStepResult(observation, "results_reached", 0)
            if not state.active_action.meaningful and not state.initiative and all(
                command.command == 0 for command in state.stored_commands
            ):
                self.driver.begin_at_pre_menu()
                return BattleStepResult(observation, "next_round_pre_menu", 0)
            return BattleStepResult(self.controller.observe_stable(), "execution_wait", 0)

        if stage == BattleInputStage.RESULTS:
            after = self.controller.finish_battle_results()
            after_state = BattleState.from_wram(after.wram)
            if not after_state.game.in_battle:
                self.driver.session.stage = BattleInputStage.UNKNOWN
                return BattleStepResult(after, "results_complete", 1)
            raise RuntimeError("Held A through result flow, but battle mode remained active")

        raise RuntimeError(
            "Battle UI hierarchy is unknown. Resume requires an explicit confirmed stage; no input sent."
        )
