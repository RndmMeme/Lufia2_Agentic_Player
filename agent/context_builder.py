"""Build the LLM context from the current game observation."""

from __future__ import annotations

from typing import Any

from agent.dungeon_context import DungeonContextRegistry
from agent.dungeons import get_dungeon
from agent.established_memory import global_memory_context
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
        room_reset_recovery: dict | None = None,
    ) -> list[str]:
        """Return the available actions filtered by the current situation."""
        actions = ["move(direction,count=1..4)", "face(direction) using R+direction without moving"]

        # A alone handles NPCs/chests; direction+A is also needed to probe
        # pushable, pickable, or otherwise directional dungeon objects.
        actions.append("interact(direction optional) using A or hold-A+direction-impulse")

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

        # Reset is destructive to the current room state. It is exposed only
        # when curated room policy and observed action outcomes jointly produce
        # a recovery ticket; it is never a generic exploration action.
        if (room_reset_recovery or {}).get("eligible"):
            actions.append("reset_room (conditional puzzle recovery)")

        return actions

    @staticmethod
    def _room_reset_recovery(navigation: dict, recent_agent_actions: list) -> dict:
        """Issue a conservative reset ticket from curated and observed evidence."""
        room = navigation.get("current_room", {})
        policy = room.get("reset_policy")
        if not isinstance(policy, dict) or not policy.get("enabled"):
            return {
                "eligible": False,
                "reason": "current room has no curated reset policy",
            }

        actions = list(recent_agent_actions)
        last_reset = max(
            (index for index, action in enumerate(actions) if action.get("kind") == "reset_room"),
            default=-1,
        )
        mutation_kinds = set(policy.get("mutation_actions", ["interact", "sword", "use_tool"]))
        mutation_index = None
        for index in range(last_reset + 1, len(actions)):
            action = actions[index]
            if (
                action.get("kind") in mutation_kinds
                and int(action.get("map_tile_change_count", 0)) > 0
                and not action.get("completed_landmark")
            ):
                mutation_index = index
        if mutation_index is None:
            return {
                "eligible": False,
                "reason": "no unconfirmed puzzle-state mutation observed since the last room reset",
                "policy": policy,
            }

        # Walking near a puzzle object is exploration, not an attempted state
        # correction. Only directed interactions can probe whether a prior
        # movable-object mutation is still recoverable.
        probe_kinds = set(policy.get("failure_probe_actions", ["interact"]))
        failed = []
        for action in actions[mutation_index + 1:]:
            if action.get("kind") not in probe_kinds:
                continue
            unchanged = action.get("before", {}).get("position") == action.get("after", {}).get("position")
            no_effect = (
                int(action.get("map_tile_change_count", 0)) == 0
                and not action.get("navigation_relevant_change")
            )
            if unchanged and no_effect:
                failed.append({
                    "kind": action.get("kind"),
                    "position": action.get("after", {}).get("position"),
                    "direction": action.get("requested_direction"),
                })

        required = max(1, int(policy.get("minimum_failed_actions_after_mutation", 2)))
        eligible = len(failed) >= required
        return {
            "eligible": eligible,
            "reason": (
                "curated resettable puzzle was changed, then repeated recovery probes had no effect"
                if eligible else
                f"puzzle changed, but only {len(failed)}/{required} ineffective recovery probes were observed"
            ),
            "failed_probe_count": len(failed),
            "required_failed_probe_count": required,
            "evidence": failed[-3:],
            "use_when": policy.get("use_when"),
            "do_not_use_when": policy.get("do_not_use_when"),
        }

    @staticmethod
    def _position_update(position: list, recent_agent_actions: list, active_landmark: dict | None) -> dict:
        """Give the model one explicit, actor-centred movement result."""
        result = {
            "current": list(position),
            "coordinate_rule": "x increases east; y increases south",
        }
        if recent_agent_actions and recent_agent_actions[-1].get("kind") == "move":
            action = recent_agent_actions[-1]
            before = action.get("before", {}).get("position") or position
            after = action.get("after", {}).get("position") or position
            dx, dy = int(after[0]) - int(before[0]), int(after[1]) - int(before[1])
            result["last_move"] = {
                "requested": {
                    "direction": action.get("requested_direction"),
                    "tiles": action.get("requested_tiles"),
                },
                "from": list(before),
                "to": list(after),
                "actual_delta": [dx, dy],
                "actual_tiles": abs(dx) + abs(dy),
                "outcome": "blocked_or_no_displacement" if dx == 0 and dy == 0 else "position_changed",
            }
        target = (
            (active_landmark or {}).get("effective_live")
            or (active_landmark or {}).get("live")
        )
        if isinstance(target, list) and len(target) == 2:
            dx = int(target[0]) - int(position[0])
            dy = int(target[1]) - int(position[1])
            result["active_target"] = {
                "id": active_landmark.get("id"),
                "position": list(target),
                "role": (
                    "next_threshold_step"
                    if (active_landmark.get("traversal") or {}).get("phase")
                    in {"threshold_ready", "crossing_threshold"}
                    else "landmark"
                ),
                "delta_from_current": [dx, dy],
                "manhattan_tiles": abs(dx) + abs(dy),
            }
        return result

    @staticmethod
    def _restrict_fully_ready_landmark_action(
        actions: list[str], navigation: dict, selected_tool: str | None = None
    ) -> list[str]:
        """Sequence an action landmark only after its exact position is reached.

        En route, keep the full action set available: tools may still be useful
        for enemies or another local object.  Once the actor is standing on the
        curated action coordinate, advertise only the missing precondition or
        the final action.  This avoids making the model rediscover action
        semantics without constraining its route through the room.
        """
        room = navigation.get("current_room", {})
        landmark = navigation.get("active_landmark")
        if not isinstance(landmark, dict) or not landmark:
            landmark = next(
                (
                    item
                    for item in room.get("nearby_live_landmarks", [])
                    if item.get("active") and not item.get("completed")
                ),
                None,
            )
        if not landmark:
            return actions

        readiness = landmark.get("action_readiness", {})
        if readiness.get("completed") or not readiness.get("position_ready"):
            return actions

        def only(kind: str) -> list[str]:
            matching = [
                action
                for action in actions
                if str(action).split(" ", 1)[0].split("(", 1)[0] == kind
            ]
            return matching or actions

        required = landmark.get("action")
        required_tool = landmark.get("tool")
        if required == "use_tool" and required_tool and selected_tool != required_tool:
            return only("select_tool")
        if not readiness.get("facing_ready"):
            return only("face")
        if readiness.get("next_precondition") is None and required in {
            "use_tool", "sword", "interact"
        }:
            return only(required)
        return actions

    @staticmethod
    def _suppress_unresolved_transit_context(
        navigation: dict, navigation_map: dict
    ) -> tuple[dict, bool]:
        """Hide the previous room's priors after a traversal boundary.

        Some internal room transitions keep the same map id and overlapping
        WRAM coordinates.  Once a directed traversal segment has ended, the
        old curated room map is actively misleading until the mapper can
        resolve a new stable room.  Keep live position, screenshot, and the
        actor-local tile buffer available, but make this uncertainty explicit.
        """
        segment = navigation.get("completed_traversal_segment")
        if not isinstance(segment, dict) or not segment:
            return navigation_map, False

        previous_room = navigation.get("current_room", {})
        navigation.pop("active_landmark", None)
        navigation["previous_room_context"] = {
            "id": previous_room.get("id") if isinstance(previous_room, dict) else None,
            "status": "left_via_completed_traversal_segment",
        }
        navigation["local_layout_resolution"] = {
            "status": "unresolved_after_transit",
            "instruction": (
                "Explore the current local layout and find a passable exit. "
                "Use live screenshot, actor-local tiles, movement, and collision feedback."
            ),
            "stale_context_suppressed": True,
        }
        navigation["current_room"] = {
            "id": None,
            "resolved": False,
            "objective": "Explore the current local layout and find a passable exit.",
            "success_evidence": "A new stable room or layout transition is observed.",
            "nearby_live_landmarks": [],
        }
        return {
            "available": False,
            "reason": (
                "The curated map belongs to the previous room context and is "
                "suppressed until the live room transition resolves."
            ),
            "local_policy": (
                "Use the screenshot, actor-local tile buffer, collision feedback, "
                "and reversible movement to explore this transit layout."
            ),
            "nearby_curated_markers": [],
        }, True

    @staticmethod
    def _local_route_evidence(
        navigation: dict, recent_agent_actions: list | None = None
    ) -> dict:
        """Summarize tested WRAM edges at the actor's exact current tile."""
        reverse_direction = {"north": "south", "south": "north", "west": "east", "east": "west"}
        recent_non_progressing = None
        if recent_agent_actions:
            last = recent_agent_actions[-1]
            traversal_count = int(
                (last.get("feedback") or {}).get("local_edge_traversal_count", 0)
            )
            moved = last.get("before", {}).get("position") != last.get("after", {}).get("position")
            requested = last.get("requested_direction")
            if last.get("kind") == "move" and moved and requested and traversal_count >= 3:
                recent_non_progressing = {
                    "reverse_from_current": reverse_direction.get(requested),
                    "traversal_count": traversal_count,
                    "status": "deprioritize_now_not_forbidden",
                    "reason": "this immediate reverse continues the observed A-B-A-B loop",
                }
        observed = navigation.get("observed_edges", {})
        passable = []
        impassable_now = []
        for direction in ("north", "south", "west", "east"):
            edge = observed.get(direction)
            if not isinstance(edge, dict):
                continue
            outcome = edge.get("outcome")
            if outcome in {"open", "transition"} and edge.get("to"):
                passable.append({
                    "direction": direction,
                    "to": edge.get("to"),
                    "evidence": "WRAM-confirmed traversal",
                    "recent_non_progressing": bool(
                        recent_non_progressing
                        and direction == recent_non_progressing.get("reverse_from_current")
                    ),
                })
            elif outcome == "blocked_now":
                impassable_now.append({
                    "direction": direction,
                    "evidence": "WRAM-confirmed collision in this direction and state",
                })
        return {
            "scope": "actor's exact current feet coordinate and current room state",
            "passable": passable,
            "impassable_now": impassable_now,
            "untried": list(navigation.get("unknown_directions", [])),
            "recent_non_progressing_edge": recent_non_progressing,
            "instruction": (
                "Use tested WRAM movement over a conflicting visual guess. During stagnation, "
                "prefer a passable or untried local edge not marked recent_non_progressing. "
                "The marked edge remains legal when deliberate backtracking is actually required."
            ),
        }

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
        dungeon_instance = dungeon_cls(None) if dungeon_cls is not None else None
        if mapper is not None:
            room_context = navigation.get("current_room", {})
            active_landmark = (
                dungeon_instance.navigation_target(observation, mapper, room_context)
                if dungeon_instance is not None else None
            )
            if active_landmark is None:
                active_landmark = mapper.next_room_landmark(room_context)
            if active_landmark is not None:
                active_id = active_landmark.get("id")
                completed_segment = mapper.completed_traversal_segment(
                    room_context.get("id"), active_id
                )
                landmarks = room_context.get("nearby_live_landmarks", [])
                for landmark in landmarks:
                    is_target = landmark.get("id") == active_id
                    landmark["active"] = is_target and completed_segment is None
                    if is_target and completed_segment is not None:
                        landmark["completed"] = True
                        landmark.setdefault("checkpoint", {})["status"] = completed_segment.get("status")
                if completed_segment is None:
                    navigation["active_landmark"] = active_landmark
                    landmarks.sort(key=lambda item: 0 if item.get("active") else 1)
                else:
                    navigation["completed_traversal_segment"] = completed_segment
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
        visible_object_candidates = self.tile_buffers.object_candidates(
            observation.game.map_id,
            observation.game.x,
            observation.game.y,
            observation.wram,
            radius=4,
        )
        if dungeon_instance is not None:
            provisional_target = dungeon_instance.provisional_object_target(
                observation,
                navigation.get("current_room", {}),
                visible_object_candidates,
            )
            if provisional_target:
                navigation["provisional_object_target"] = provisional_target
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

        navigation_map, unresolved_transit = self._suppress_unresolved_transit_context(
            navigation, navigation_map
        )
        navigation["local_route_evidence"] = self._local_route_evidence(
            navigation, recent_agent_actions
        )
        if unresolved_transit:
            # Correlation against the previous room's curated edges would turn
            # a live collision into false wall evidence in the transit layout.
            spatial_correlation = self._spatial_correlation(
                [observation.game.x, observation.game.y],
                blocked_direction,
                actor_tile_buffer,
                None,
                {},
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

        room_reset_recovery = self._room_reset_recovery(navigation, recent_agent_actions)
        available_actions = self._available_actions(
            observation, mapper, selected_tool, reasoning_evidence, room_reset_recovery
        )
        if unresolved_transit:
            available_actions = [
                action for action in available_actions
                if str(action).split(" ", 1)[0].split("(", 1)[0] != "look_map"
            ]
        available_actions = self._restrict_fully_ready_landmark_action(
            available_actions, navigation, selected_tool
        )
        available_kinds = {
            str(action).split(" ", 1)[0].split("(", 1)[0]
            for action in available_actions
        }
        perception_exhausted = not ({"look", "look_map"} & available_kinds)
        room_context = navigation.get("current_room", {})
        dungeon_memory = (
            dungeon_instance.established_memory(observation, room_context)
            if dungeon_instance is not None else []
        )
        room_objective = str(room_context.get("objective") or "").casefold()
        movable_object = any(
            token in room_objective for token in ("pillar", "vase", "push", "button")
        ) or bool(navigation.get("tracked_movable_object"))
        after_reset = bool(
            recent_agent_actions
            and recent_agent_actions[-1].get("kind") == "reset_room"
        )
        at_threshold = any("threshold" in str(item.get("id", "")) for item in dungeon_memory)
        established_memory = {
            "policy": (
                "Run-independent established facts only. Live state decides whether a conditional fact applies; "
                "never turn an unverified model hypothesis into memory."
            ),
            "global": global_memory_context(
                observation.game.mode,
                blocked=bool(blocked_direction),
                movable_object=movable_object,
                after_reset=after_reset,
                at_threshold=at_threshold,
            ),
            "dungeon": dungeon_memory,
        }

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
            "position_update": self._position_update(
                [observation.game.x, observation.game.y],
                recent_agent_actions,
                navigation.get("active_landmark"),
            ),
            "strategic_progression": strategic_progression,
            "dungeon_context": self.dungeons.context(
                observation.game.map_id, observation.game.x, observation.game.y, radius=9
            ),
            "navigation_map": navigation_map,
            "tile_buffer": actor_tile_buffer,
            "visible_object_candidates": visible_object_candidates,
            "spatial_correlation": spatial_correlation,
            "tutorial": self.tutorial.context(
                observation.game.map_id, observation.game.x, observation.game.y
            ),
            "established_memory": established_memory,
            "selected_dungeon_tool": selected_tool,
            "exploration_relevant_items": exploration_relevant_items,
            "available_actions": available_actions,
            "room_reset_recovery": room_reset_recovery,
            "recent_agent_actions": recent_agent_actions,
            "feedback": feedback.context(),
            "navigation": navigation,
            "recent_events": mapper.state["events"][-6:] if mapper else [],
            "reasoning_evidence": reasoning_evidence,
        }
