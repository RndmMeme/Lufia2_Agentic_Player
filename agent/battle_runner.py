"""Extracted battle loop from the orchestrator."""

from __future__ import annotations

from typing import Any

from agent.battle import BattleCoordinator
from agent.model_gateway import ModelGateway
from agent.watchdog import ModelStallError


class BattleRunner:
    """Runs the battle loop with model-based tactical decisions."""

    def __init__(self, battle: BattleCoordinator, model_gateway: ModelGateway, journal: Any, feedback_manager: Any) -> None:
        self.battle = battle
        self.model_gateway = model_gateway
        self.journal = journal
        self.feedback_manager = feedback_manager
        self.active = False

    def step(self, observation: Any, started_inside_battle: bool, actions: int, resume_stage: str | None, resume_actor: int) -> tuple[Any, int, str | None]:
        """Run one battle step. Returns (observation, actions_used, stop_reason)."""
        if not self.active:
            if started_inside_battle and actions == 0:
                if resume_stage == "pre_menu":
                    self.battle.driver.begin_at_pre_menu()
                elif resume_stage == "action_cross":
                    self.battle.driver.resume_at_action_cross(resume_actor)
                elif resume_stage == "results":
                    self.battle.driver.resume_at_results()
                else:
                    return observation, 0, "battle_resume_stage_required"
                self.journal.write(
                    "battle_resumed",
                    ui_stage=resume_stage,
                    actor_slot=resume_actor,
                )
            else:
                self.battle.begin_new_battle()
            self.active = True
            self.journal.write("battle_started", state=observation.game.compact())

        before_step = observation
        try:
            result = self.battle.step(observation)
        except (ModelStallError, RuntimeError, ValueError, OSError) as exc:
            attempted = self.battle.driver.last_input_count
            self.journal.write(
                "battle_step_rejected",
                error=str(exc),
                ui_stage=self.battle.driver.session.stage.value,
                attempted_inputs=attempted,
            )
            return observation, attempted, "battle_step_rejected"

        observation = result.observation
        if result.inputs:
            self.feedback_manager.remember_action(
                "battle_step",
                before_step,
                observation,
                battle_event=result.event,
                ui_stage=self.battle.driver.session.stage.value,
                inputs=result.inputs,
            )
        self.journal.write(
            "battle_step",
            battle_event=result.event,
            inputs=result.inputs,
            ui_stage=self.battle.driver.session.stage.value,
            state=observation.game.compact(),
        )
        if not observation.game.in_battle:
            self.active = False
            return observation, result.inputs, None
        return observation, result.inputs, None
