"""Build the LLM context from the current game observation."""

from __future__ import annotations

from typing import Any

from agent.dungeon_context import DungeonContextRegistry
from agent.dungeons import get_dungeon
from agent.progression import ProgressionPlanner
from agent.tutorial_guide import TutorialGuide

DUNGEON_TOOLS = (
    ("hook", "Hook"),
    ("bomb", "Bomb"),
    ("arrow", "Arrow"),
    ("fire_arrow", "Fire Arrow"),
    ("hammer", "Hammer"),
)


class ContextBuilder:
    """Builds the compact LLM context from the current game observation."""

    def __init__(self, progression: ProgressionPlanner, dungeons: DungeonContextRegistry, tutorial: TutorialGuide, tile_buffers: Any) -> None:
        self.progression = progression
        self.dungeons = dungeons
        self.tutorial = tutorial
        self.tile_buffers = tile_buffers

    def _available_actions(
        self,
        observation: Any,
        mapper: Any,
        selected_tool: str | None,
        reasoning_evidence: list | None = None,
    ) -> list[str]:
        """Return the available actions filtered by the current situation."""
        actions = ["move(direction,count=1..4)", "face(direction) using R+direction without moving"]

        # A alone handles NPCs/chests; direction+A is also needed to probe
        # pushable, pickable, or otherwise directional dungeon objects.
        actions.append("interact(direction optional) using A or direction+A")

        # sword is only available when there are bushes, enemies, or switches that can be influenced
        # For now, keep it available — the model will decide if it's useful
        actions.append("sword using B")

        # A selected but wrong tool must remain replaceable.  Hiding this action
        # traps the decision layer in the current selection.
        actions.append("select_tool(tool)")

        # use_tool is only available when a tool is selected
        if selected_tool is not None:
            actions.append("use_tool using Y")

        # A perception action is useful once per unchanged emulator state. It
        # must then result in an executable choice instead of an observation
        # loop. Any emulator action clears reasoning_evidence again.
        used_perception = {
            evidence.get("type")
            for evidence in (reasoning_evidence or [])
            if isinstance(evidence, dict)
        }
        if "look" not in used_perception:
            actions.append("look at current frame")
        if "look_map" not in used_perception:
            actions.append("look_map at current frame plus full curated dungeon map")

        # retrieve is always available for knowledge
        actions.append("retrieve(query)")

        # reset_room is only available when a puzzle state needs to be reset
        # For now, keep it available — the model will decide if it's useful
        actions.append("reset_room")

        return actions

    @staticmethod
    def _restrict_fully_ready_landmark_action(actions: list[str], navigation: dict) -> list[str]:
        """Make advertised actions agree with the existing landmark gate."""
        room = navigation.get("current_room", {})
        for landmark in room.get("nearby_live_landmarks", []):
            readiness = landmark.get("action_readiness", {})
            if readiness.get("completed"):
                continue
            if not readiness.get("position_ready"):
                continue
            required = landmark.get("action")
            fully_ready = (
                readiness.get("facing_ready")
                and readiness.get("next_precondition") is None
                and required in {"use_tool", "sword", "interact"}
            )
            if fully_ready:
                matching = [
                    action for action in actions
                    if str(action).split(" ", 1)[0].split("(", 1)[0] == required
                ]
                return matching or actions
            break
        return actions

    @staticmethod
    def _confirmed_blocked_direction(compact: dict, recent_agent_actions: list) -> str | None:
        """Expose 1272 only when it confirms the immediately attempted move.

        The byte retains the last collision direction across new runner starts
        and pure observations. Treating that stale value as a current wall can
        make the model legally unable to leave its start tile.
        """
        current = [compact.get("x"), compact.get("y")]
        for action in reversed(recent_agent_actions):
            before = action.get("before", {}).get("position")
            after = action.get("after", {}).get("position")
            if after != current:
                break
            if action.get("navigation_relevant_change"):
                break
            if action.get("kind") == "face":
                # Turning in place cannot make a collided edge passable and
                # must not erase the observation.
                continue
            if action.get("kind") != "move":
                break
            attempted = action.get("requested_direction")
            observed = action.get("after", {}).get("blocked_direction")
            if before == after and attempted and observed == attempted:
                return str(attempted)
        return None

    @staticmethod
    def _spatial_correlation(
        position: list,
        blocked_direction: str | None,
        tile_buffer: dict,
        active_landmark: dict | None,
        curated_priors: dict[str, str] | None = None,
    ) -> dict | None:
        """Correlate a failed move, adjacent WRAM tile and target vector.

        A collision byte proves only ``blocked_now``. Tile-buffer families are
        appearance/state clues and cannot distinguish a wall from a movable,
        pickable, locked, or otherwise interactive object. Only the curated
        navigation map may upgrade this to a known wall/block.
        """
        if not blocked_direction or len(position) != 2:
            return None
        vectors = {
            "north": (0, -1), "south": (0, 1),
            "west": (-1, 0), "east": (1, 0),
        }
        dx, dy = vectors[blocked_direction]
        cells = {
            tuple(cell.get("relative", [])): cell
            for cell in tile_buffer.get("cardinal_cells", [])
        }
        blocked_cell = cells.get((dx, dy), {})
        family = str(blocked_cell.get("family", "unknown"))
        curated_priors = curated_priors or {}
        curated_direction = curated_priors.get(blocked_direction, "unknown")
        map_proves_block = curated_direction == "blocked"

        target = (active_landmark or {}).get("live")
        target_components = []
        alternatives = []
        if isinstance(target, list) and len(target) == 2:
            target_dx = int(target[0]) - int(position[0])
            target_dy = int(target[1]) - int(position[1])
            if target_dx:
                target_components.append("east" if target_dx > 0 else "west")
            if target_dy:
                target_components.append("south" if target_dy > 0 else "north")
            # A target vector is a useful preference, not a local path proof.
            # Expose every other cardinal edge so the model may test north or
            # south around a wall and may deliberately backtrack when a room
            # topology requires it.
            for direction in ("north", "south", "west", "east"):
                if direction == blocked_direction:
                    continue
                cell_dx, cell_dy = vectors[direction]
                cell = cells.get((cell_dx, cell_dy), {})
                alternatives.append({
                    "direction": direction,
                    "live": cell.get("live"),
                    "tile_family": cell.get("family", "unknown"),
                    "occupied": cell.get("occupied"),
                    "target_aligned": direction in target_components,
                    "status": "locally_available_candidate",
                })

        conclusion = (
            f"Move {blocked_direction} failed; the curated map marks this edge blocked."
            if map_proves_block
            else (
                f"Move {blocked_direction} failed now. Adjacent family {family} is not wall "
                "proof; the edge may be movable, pickable, locked, conditional, or interactive."
            )
        )
        return {
            "type": "action_wram_local_tile_correlation",
            "position": list(position),
            "attempted_direction": blocked_direction,
            "position_unchanged": True,
            "collision_byte_matches_attempt": True,
            "adjacent_tile": {
                "live": blocked_cell.get("live"),
                "family": family,
                "occupied": blocked_cell.get("occupied"),
            },
            "curated_map_evidence": curated_direction,
            "map_proves_wall_or_block": map_proves_block,
            "conclusion": conclusion,
            "scope": "this edge in the current room state; only curated blocked map evidence proves a wall/block",
            "target": target,
            "target_components": target_components,
            "local_alternatives": alternatives,
            "blocked_edge_tests": (
                [] if map_proves_block else [
                    f"interact {blocked_direction} (direction+A)",
                    f"face {blocked_direction} then interact (pickup/activate)",
                    "context-justified tool",
                ]
            ),
            "next_inference": (
                f"Do not retry plain movement {blocked_direction} unchanged. Test another local edge"
                + (
                    " or an interaction with the blocked edge"
                    if not map_proves_block else ""
                )
                + "; target alignment is a preference, not proof, and backtracking remains valid."
                if alternatives
                else f"Do not retry {blocked_direction} unchanged; choose another reversible direction."
            ),
        }

    def build(self, observation: Any, goal: str, mapper: Any, feedback: Any, reasoning_evidence: list, recent_agent_actions: list) -> dict:
        """Build the raw context dict from the current observation."""
        compact = observation.game.compact()
        navigation_progress = mapper.progress() if mapper else {}
        local_objective_active = (
            int(navigation_progress.get("rooms_expected", 0)) > 0
            and not navigation_progress.get("complete", False)
        )
        if local_objective_active:
            strategic_progression = {
                "deferred": True,
                "reason": "Finish the active room-scoped dungeon objective before choosing another world destination.",
            }
        else:
            progression_result = self.progression.choose_goal(
                compact.get("progression_tokens", [])
            )
            # Access logic consumes key/scenario tokens internally.  The LLM
            # receives semantic reachability, never raw key requirements.
            strategic_progression = {
                "goal": progression_result.get("goal"),
                "reason": progression_result.get("reason"),
                "world_position": progression_result.get("world_position"),
                "accessible_locations": progression_result.get("accessible", []),
            }
        selected_tool = {
            0xA7: "hook", 0xA8: "bomb", 0xA9: "arrow", 0xAA: "fire_arrow", 0xAB: "hammer"
        }.get(observation.wram[0x0A06])

        # Add blocked direction hint to reasoning_evidence
        blocked_direction = self._confirmed_blocked_direction(compact, recent_agent_actions)
        compact["blocked_direction"] = blocked_direction
        if blocked_direction:
            reasoning_evidence = reasoning_evidence + [{
                "type": "blocked_direction",
                "message": f"The direction {blocked_direction} is currently blocked. Try a different direction.",
            }]

        navigation = mapper.context_for_llm() if mapper else {}
        dungeon_cls = get_dungeon(observation.game.map_id)
        if dungeon_cls is not None and mapper is not None:
            room_context = navigation.get("current_room", {})
            active_landmark = dungeon_cls(None).navigation_target(
                observation, mapper, room_context
            )
            if active_landmark is not None:
                navigation["active_landmark"] = active_landmark
                active_id = active_landmark.get("id")
                landmarks = room_context.get("nearby_live_landmarks", [])
                for landmark in landmarks:
                    landmark["active"] = landmark.get("id") == active_id
                landmarks.sort(key=lambda item: 0 if item.get("active") else 1)
            confirmed_effects = []
            for landmark in room_context.get("nearby_live_landmarks", []):
                if not landmark.get("completed") or not landmark.get("success_effect"):
                    continue
                completion = landmark.get("completion_evidence", {})
                stored_completion = mapper.state.get("completed_landmarks", {}).get(
                    f"{room_context.get('id')}:{landmark.get('id')}", {}
                )
                confirmed_effects.append({
                    "source_landmark": landmark.get("id"),
                    "source_live": landmark.get("live"),
                    "effect": landmark.get("success_effect"),
                    "changed_live_tiles": completion.get("changed_live_tiles", []),
                    "effect_region_after": stored_completion.get("effect_region_after"),
                    "authority": "confirmed action-linked WRAM change; persists until room reset",
                })
            if confirmed_effects:
                navigation["confirmed_world_changes"] = confirmed_effects[:3]

        actor_tile_buffer = self.tile_buffers.context(
            observation.game.map_id,
            observation.game.x,
            observation.game.y,
            observation.wram,
            radius=1,
        )
        navigation_map = self.dungeons.navigation_briefing(
            observation.game.map_id, observation.game.x, observation.game.y
        )
        curated_priors = self.dungeons.directional_priors(
            observation.game.map_id, observation.game.x, observation.game.y, distance=1
        )
        spatial_correlation = self._spatial_correlation(
            [observation.game.x, observation.game.y],
            blocked_direction,
            actor_tile_buffer,
            navigation.get("active_landmark"),
            curated_priors,
        )

        previous_direction = None
        if recent_agent_actions:
            previous = recent_agent_actions[-1]
            previous_direction = (
                previous.get("requested_direction")
                or previous.get("before", {}).get("direction")
            )
        compact["previous_direction"] = previous_direction

        owned = {str(item).casefold() for item in compact.get("progression_tokens", [])}
        required_tools = {
            str(tool).casefold()
            for tool in (mapper.objective.get("required_tools", []) if mapper else [])
        }
        exploration_relevant_items = [
            {
                "name": tool_id,
                "display_name": display_name,
                "available": display_name.casefold() in owned,
                "selected": selected_tool == tool_id,
                "locally_required": tool_id in required_tools,
                "utility": "puzzle progression and enemy stun/avoidance",
            }
            for tool_id, display_name in DUNGEON_TOOLS
        ]

        available_actions = self._available_actions(
            observation, mapper, selected_tool, reasoning_evidence
        )
        available_actions = self._restrict_fully_ready_landmark_action(
            available_actions, navigation
        )
        available_kinds = {
            str(action).split(" ", 1)[0].split("(", 1)[0]
            for action in available_actions
        }
        perception_exhausted = not ({"look", "look_map"} & available_kinds)

        return {
            "goal": goal,
            "decision_phase": {
                "mode": "act_now" if perception_exhausted else "observe_or_act",
                "instruction": (
                    "Choose one executable emulator action now. Direction, detour, "
                    "interaction, and backtracking remain your choice."
                    if perception_exhausted else
                    "You may inspect remaining perception once or execute an emulator action."
                ),
                "unavailable_until_state_changes": (
                    ["look", "look_map"] if perception_exhausted else []
                ),
            },
            "game": compact,
            "strategic_progression": strategic_progression,
            "dungeon_context": self.dungeons.context(
                observation.game.map_id, observation.game.x, observation.game.y, radius=9
            ),
            "navigation_map": navigation_map,
            "tile_buffer": actor_tile_buffer,
            "spatial_correlation": spatial_correlation,
            "tutorial": self.tutorial.context(
                observation.game.map_id, observation.game.x, observation.game.y
            ),
            "selected_dungeon_tool": selected_tool,
            "exploration_relevant_items": exploration_relevant_items,
            "available_actions": available_actions,
            "recent_agent_actions": recent_agent_actions,
            "feedback": feedback.context(),
            "navigation": navigation,
            "recent_events": mapper.state["events"][-6:] if mapper else [],
            "reasoning_evidence": reasoning_evidence,
        }
