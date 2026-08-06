"""Execute emulator actions for all intent types."""

from __future__ import annotations

from typing import Any

from agent.intent import Intent
from agent.mesen_controller import MesenController


class ActionExecutor:
    """Executes emulator actions for all intent types."""

    def __init__(self, controller: MesenController) -> None:
        self.controller = controller

    def execute(self, intent: Intent, observation: Any) -> tuple[Any, int]:
        """Execute an intent and return (new_observation, action_count)."""
        if intent.kind == "move":
            observation = self.controller.move(intent.direction, tiles=intent.count)
            return observation, 1
        if intent.kind == "face":
            observation = self.controller.face(intent.direction)
            return observation, 1
        if intent.kind == "interact":
            observation = self.controller.interact(intent.direction)
            return observation, 1
        if intent.kind == "sword":
            observation = self.controller.swing_sword()
            return observation, 1
        if intent.kind == "select_tool":
            observation = self.controller.select_tool(intent.tool)
            return observation, 1
        if intent.kind == "use_tool":
            observation = self.controller.use_tool()
            return observation, 1
        if intent.kind == "reset_room":
            _, observation = self.controller.reset_room()
            return observation, 3
        if intent.kind == "wait":
            observation = self.controller.observe_stable()
            return observation, 1
        raise ValueError(f"Unsupported intent kind for execution: {intent.kind!r}")
