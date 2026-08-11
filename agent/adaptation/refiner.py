"""Conservative shadow-mode harness refiner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .harness_state import ShadowHarnessState
from .trajectory_window import TrajectoryWindow
from .validator import HarnessProposalValidator


class ShadowHarnessRefiner:
    """Generate inert, versioned suggestions from bounded trajectory evidence."""

    def __init__(
        self,
        config: dict,
        run_dir: Path,
        model: Any,
        journal: Any,
        global_context: Any = None,
    ) -> None:
        self.config = dict(config or {})
        self.enabled = bool(self.config.get("enabled", False))
        self.mode = str(self.config.get("mode", "shadow"))
        if self.enabled and self.mode not in {"shadow", "gated"}:
            raise ValueError("harness_evolution.mode must be shadow or gated")
        self.model = model
        self.journal = journal
        self.global_context = global_context
        self.window = TrajectoryWindow(
            run_dir,
            max_actions=int(self.config.get("max_window_actions", 24)),
            max_journal_events=int(self.config.get("max_journal_events", 24)),
            max_chars=int(self.config.get("max_evidence_chars", 9000)),
        )
        self.validator = HarnessProposalValidator(
            int(self.config.get("max_proposals_per_area", 3))
        )
        self.state = ShadowHarnessState(run_dir) if self.enabled else None
        self.last_refined_action = (
            self.state.last_action_index() if self.state is not None else 0
        )

    def maybe_refine(
        self,
        current_action: int,
        explicit_reason: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled or not self.model.config.get("enabled", False):
            return None
        assert self.state is not None
        records = self.window.action_records()
        new_records = [
            record for record in records
            if int(record.get("index", 0)) > self.last_refined_action
        ]
        if not new_records:
            return None
        minimum = int(self.config.get("min_window_actions", 4))
        if explicit_reason is None and len(new_records) < minimum:
            return None
        cooldown = int(self.config.get("cooldown_actions", 4))
        if explicit_reason is None and current_action - self.last_refined_action < cooldown:
            return None
        trigger = explicit_reason or self.window.detect_trigger(records)
        if not trigger:
            return None

        evidence = self.window.build(trigger)
        if self.global_context is not None:
            global_context = self.global_context()
            if global_context:
                evidence["harness_state"] = global_context
        action_range = evidence.get("action_index_range")
        evidence_indices = {
            int(record["index"])
            for record in evidence.get("actions", [])
            if isinstance(record.get("index"), int)
        }
        try:
            raw = self.model.refine_harness(evidence)
            active_ids = {
                str(item.get("id"))
                for values in evidence.get("harness_state", {}).get("active", {}).values()
                for item in values
                if item.get("id")
            }
            proposals = self.validator.validate(
                raw,
                evidence_indices,
                active_ids,
                allowed_scopes=set(
                    evidence.get("scope_context", {}).get("allowed_scopes", [])
                ),
            )
            record = self.state.write(
                trigger=trigger,
                action_range=action_range,
                status="proposed_not_applied",
                proposals=proposals,
            )
        except Exception as exc:  # shadow refinement must never stop gameplay
            record = self.state.write(
                trigger=trigger,
                action_range=action_range,
                status="rejected_or_failed",
                error=str(exc)[:1200],
            )
        self.last_refined_action = max(evidence_indices, default=current_action)
        self.journal.write(
            "harness_refinement_shadow",
            generation=record["generation"],
            trigger=trigger,
            status=record["status"],
            action_index_range=action_range,
        )
        return record
