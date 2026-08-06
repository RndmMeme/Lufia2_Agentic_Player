"""Manage action feedback, reasoning evidence, and the feedback ledger."""

from __future__ import annotations

from typing import Any

from agent.action_recorder import ActionOutcomeRecorder
from agent.feedback import FeedbackLedger


class FeedbackManager:
    """Manages action feedback, reasoning evidence, and the feedback ledger."""

    def __init__(self, feedback: FeedbackLedger, action_recorder: ActionOutcomeRecorder, mapper: Any, tile_buffers: Any, run_dir: Any) -> None:
        self.feedback = feedback
        self.action_recorder = action_recorder
        self.mapper = mapper
        self.tile_buffers = tile_buffers
        self.run_dir = run_dir
        self.reasoning_evidence: list = []
        self.recent_agent_actions: list = []
        self.reasoning_steps: int = 0
        self.stall_repeats: int = 0

    def remember_action(self, kind: str, before: Any, after: Any, navigation_event: dict | None = None, **details: Any) -> dict:
        """Record an action and its outcome, update feedback ledger and recent actions."""
        previous_action = self.recent_agent_actions[-1] if self.recent_agent_actions else None
        if (
            kind == "move"
            and previous_action
            and previous_action.get("kind") == "move"
            and previous_action.get("before", {}).get("position") == [after.game.x, after.game.y]
            and previous_action.get("after", {}).get("position") == [before.game.x, before.game.y]
            and not (navigation_event or {}).get("new_room")
        ):
            details["immediate_backtrack"] = True
        tile_diff = self.tile_buffers.diff(
            before.game.map_id,
            before.wram,
            after.wram,
            ignore_live_points={
                (before.game.x, before.game.y),
                (after.game.x, after.game.y),
            },
        ) if before.game.map_id == after.game.map_id else {
            "available": False, "count": 0, "changes": []
        }
        effect_region = self.tile_buffers.effect_context(
            after.game.map_id,
            tile_diff.get("changes", []),
            after.wram,
            radius=1,
        )
        if effect_region.get("available"):
            tile_diff["effect_region_after"] = effect_region
        details = {
            **details,
            "map_tile_change_count": int(tile_diff.get("semantic_count", 0)),
            "map_tile_observation_count": int(tile_diff.get("count", 0)),
            "map_tile_changes": tile_diff.get("changes", []),
            "map_effect_region_after": tile_diff.get("effect_region_after"),
        }
        details["navigation_relevant_change"] = bool(
            before.game.map_id != after.game.map_id
            or (before.game.x, before.game.y) != (after.game.x, after.game.y)
            or before.game.mode != after.game.mode
            or before.game.event_flags != after.game.event_flags
            or before.game.dungeon_flags != after.game.dungeon_flags
            or details["map_tile_change_count"] > 0
            or kind == "reset_room"
        )
        completed_landmark = None
        if self.mapper is not None:
            completed_landmark = self.mapper.record_action_landmark_effect(
                kind, before.navigation, tile_diff
            )
        if completed_landmark:
            details["completed_landmark"] = completed_landmark
            self.mapper.save(self.run_dir / "online_navigation_graph.json")
        feedback = self.feedback.record(
            kind, before, after, navigation_event=navigation_event, **details
        )
        self.recent_agent_actions.append({
            "kind": kind,
            "before": {
                "position": [before.game.x, before.game.y],
                "direction": before.game.direction,
                "mode": before.game.mode,
            },
            "after": {
                "position": [after.game.x, after.game.y],
                "direction": after.game.direction,
                "mode": after.game.mode,
                "blocked_direction": after.game.blocked_direction,
            },
            "feedback": feedback,
            **details,
        })
        self.recent_agent_actions = self.recent_agent_actions[-6:]
        self.action_recorder.record(
            kind,
            before,
            after,
            feedback,
            navigation_event=navigation_event,
            tile_diff=tile_diff,
            **details,
        )
        return feedback

    def clear_reasoning(self, action_feedback: dict | None = None) -> None:
        """Start a fresh bounded reasoning cycle after an emulator action."""
        self.reasoning_evidence = []
        self.reasoning_steps = 0
        self.stall_repeats = 0

    def add_evidence(self, evidence: dict) -> None:
        """Append an evidence entry to reasoning_evidence."""
        self.reasoning_evidence.append(evidence)

    def increment_reasoning_steps(self) -> None:
        """Increment the reasoning step counter."""
        self.reasoning_steps += 1

    def increment_stall_repeats(self) -> None:
        """Increment the stall repeat counter."""
        self.stall_repeats += 1

    def reset_stall_repeats(self) -> None:
        """Reset the stall repeat counter."""
        self.stall_repeats = 0
