"""Gateway for all model interactions: intent, look, look_map, battle."""

from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from agent.intent import Intent
from agent.model_client import LocalModelClient
from agent.watchdog import DecisionWatchdog, ModelStallError
from agent.battle import BattleDecision, BattleOption


class ModelGateway:
    """Handles all model interactions with watchdog and error handling."""

    def __init__(
        self,
        model: LocalModelClient,
        watchdog: DecisionWatchdog,
        journal: Any,
        thinking_gate: Any,
        action_count: Callable[[], int] | None = None,
    ) -> None:
        self.model = model
        self.watchdog = watchdog
        self.journal = journal
        self.thinking_gate = thinking_gate
        self.action_count = action_count or (lambda: 0)

    def ask_intent(
        self,
        context: dict,
        max_move_batch: int,
        frames: list[Path] | None = None,
    ) -> Intent:
        """Ask the model for an intent with watchdog and thinking gate validation."""
        started = time.monotonic()

        def choose(candidate_context: dict) -> Intent:
            if frames:
                return self.model.choose_intent(
                    candidate_context, max_move_batch, frames=frames
                )
            return self.model.choose_intent(candidate_context, max_move_batch)

        def bark(elapsed: float) -> None:
            message = (
                f"[LLM watchdog] {elapsed:.0f}s without a decision; "
                "emulator input remains paused."
            )
            print(message, flush=True)
            self.journal.write(
                "model_watchdog_bark",
                elapsed_seconds=round(elapsed, 3),
                action=self.action_count(),
                state_fingerprint=list(self.thinking_gate.fingerprint(context)),
            )

        # First attempt
        try:
            intent, elapsed = self.watchdog.run(
                lambda: choose(context),
                bark,
            )
            self.thinking_gate.validate(intent, context, elapsed)
            self.journal.write(
                "model_intent",
                intent=asdict(intent),
                elapsed_seconds=round(time.monotonic() - started, 3),
                context_budget=context.get("context_budget"),
                perception=(
                    f"structured_state_plus_{len(frames)}_chronological_frames"
                    if frames else
                    "structured_state_only; use look or look_map for an on-demand screenshot"
                ),
            )
            return intent
        except (ValueError, RuntimeError) as exc:
            # Retry with a clearer instruction if the model produced an invalid format
            error_msg = str(exc)
            if "Unsupported intent kind" in error_msg or "no JSON object" in error_msg:
                repair_context = dict(context)
                repair_context["format_error"] = (
                    f"Your previous response was invalid: {error_msg[:200]}. "
                    "Return ONLY a JSON object with exactly these fields: kind, direction, count, "
                    "question, query, tool, rationale. Use null for unused optional values. "
                    "Do NOT use exploration_direction, move_direction, action, action_type, or intent."
                )
                intent, elapsed = self.watchdog.run(
                    lambda: choose(repair_context),
                    bark,
                )
                self.thinking_gate.validate(intent, context, elapsed)
                self.journal.write(
                    "model_intent_repaired",
                    intent=asdict(intent),
                    elapsed_seconds=round(time.monotonic() - started, 3),
                    repair_reason=error_msg[:200],
                    context_budget=context.get("context_budget"),
                )
                return intent
            raise

    def ask_battle(
        self,
        battle_state: dict,
        legal_options: list[BattleOption],
        tactical_advisory: dict,
    ) -> BattleDecision:
        """Ask the model for a battle decision with watchdog."""
        started = time.monotonic()

        def bark(elapsed: float) -> None:
            print(
                f"[Battle LLM watchdog] {elapsed:.0f}s without a decision; "
                "emulator input remains paused.",
                flush=True,
            )
            self.journal.write(
                "battle_model_watchdog_bark",
                elapsed_seconds=round(elapsed, 3),
                ui_stage=battle_state.get("ui_stage"),
            )

        decision, elapsed = self.watchdog.run(
            lambda: self.model.choose_battle_action(
                battle_state,
                legal_options,
                tactical_advisory,
            ),
            bark,
        )
        self.journal.write(
            "battle_model_decision",
            decision=asdict(decision),
            legal_option_ids=[option.resolved_id for option in legal_options],
            ui_stage=battle_state.get("ui_stage"),
            elapsed_seconds=round(elapsed, 3),
            total_elapsed_seconds=round(time.monotonic() - started, 3),
        )
        return decision

    def look(self, frame_path: Path, context: dict, question: str) -> dict:
        """Ask the model to look at a frame."""
        if not self.model.config.get("enabled", False):
            return {"status": "queued_no_model", "frame": str(frame_path), "question": question}
        return self.model.look(frame_path, context, question)

    def look_map(self, frame_path: Path, context: dict, question: str, map_path: Path | None = None) -> dict:
        """Ask the model to look at a frame plus map."""
        if not self.model.config.get("enabled", False):
            return {"status": "queued_no_model", "frame": str(frame_path), "map": str(map_path), "question": question}
        return self.model.look(frame_path, context, question, map_frame=map_path)
