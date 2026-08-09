"""Secret Skills Cave specific puzzle and feedback logic."""

from __future__ import annotations

from typing import Any

from .base import BaseDungeon


class SecretSkillsCave(BaseDungeon):
    """Secret Skills Cave (map_id=5) with the arrow-bridge puzzle."""

    map_id: int = 5
    name: str = "Secret Skills Cave"

    # Map buffer formula for map_id=5 (from docs/map_buffer_notes.md)
    MAP_BASE: int = 0x4000
    MAP_STRIDE: int = 0x3A

    # Bridge tiles from HANDOVER.md
    BRIDGE_TILES: list[tuple[int, int]] = [(24, 26), (24, 27), (24, 28)]

    ROOM_MEMORY: dict[str, tuple[dict, ...]] = {
        "room_2": (
            {
                "id": "room2_north_threshold",
                "form": "binary",
                "when": "actor feet are at live [28,32] while moving north",
                "then": "this is still the room-2 doorway threshold; room 3 is confirmed only at live [28,31]",
                "authority": "user correction plus live Mesen step capture",
            },
        ),
        "room_3": (
            {
                "id": "room3_forward_bridge_action",
                "form": "binary",
                "when": "forward leg and bridge is inactive",
                "then": "reach live [28,24], face west, ensure Arrow is selected, and use_tool exactly once",
                "authority": "curated dungeon solution plus confirmed WRAM bridge effect",
            },
            {
                "id": "room3_after_bridge_activation",
                "form": "binary",
                "when": "Arrow use changed the bridge to active",
                "then": "do not fire again; cross toward live [21,26], reach [17,23], then move west through the left-side door",
                "authority": "confirmed action-linked WRAM change and successful traversal",
            },
        ),
        "room_4": (
            {
                "id": "room4_floor_button_receiver",
                "form": "object_intent",
                "movable": "pillar",
                "initial_live": [8, 21],
                "alignment_push_direction": "west",
                "required_live": [4, 20],
                "actor_forbidden_live": [4, 20],
                "ephemeral_barrier_live": [
                    [4, 19], [5, 19], [6, 19], [7, 19], [8, 19],
                    [4, 21], [5, 21], [6, 21], [7, 21],
                ],
                "opening_push": {
                    "when_object_live": [8, 21],
                    "actor_target_live": [8, 22],
                    "interact_direction": "north",
                    "result_object_live": [8, 20],
                },
                "alignment_entry": {
                    "when_object_live": [8, 20],
                    "actor_route_live": [[9, 21], [9, 20]],
                },
                "solved_exit": {
                    "actor_route_live": [
                        [6, 20], [6, 19], [6, 18], [6, 17],
                        [6, 16], [6, 15], [6, 14],
                    ],
                    "transition_direction": "north",
                },
                "anchor_semantics": "pillar current_live is its lower foot/base tile (map value 08); the upper sprite tile (40) never counts as switch occupancy",
                "coordinate_rule": "x increases east and y increases south; therefore a smaller x is west and a smaller y is north",
                "constraint": "Guy is only the pusher and must never be routed onto the floor button; proximity or an intermediate push is not success",
                "then": "push north exactly once from initial_live to [8,20], enter the east side via [9,21] then [9,20], and push west; success iff pillar current_live equals required_live, then verify and use the open north door",
                "authority": "user-positioned live Mesen solved-state capture",
            },
            {
                "id": "room4_reset_condition",
                "form": "binary",
                "when": "the pillar has actually been pushed against a wall and can no longer be repositioned",
                "then": "reset_room is valid only before leaving room 4; after any room transition in Secret Skills Cave, never reset because the previous room becomes unreachable",
                "authority": "user-curated puzzle mechanic",
            },
        ),
    }

    def tile_address(self, x: int, y: int) -> int:
        return self.MAP_BASE + x + y * self.MAP_STRIDE

    def established_memory(
        self, observation: Any, room_context: dict
    ) -> list[dict]:
        room_id = str(room_context.get("id") or "")
        return [dict(item) for item in self.ROOM_MEMORY.get(room_id, ())]

    def provisional_object_target(
        self, observation: Any, room_context: dict, candidates: dict
    ) -> dict | None:
        if room_context.get("id") != "room_4":
            return None
        candidate = next(
            (
                item for item in candidates.get("candidates", [])
                if item.get("family") == "obstacle" and item.get("live") == [8, 21]
            ),
            None,
        )
        if candidate is None:
            return None
        relative = list(candidate.get("relative") or [])
        if len(relative) != 2:
            return None
        directions = []
        if relative[0]:
            directions.append((abs(relative[0]), "east" if relative[0] > 0 else "west"))
        if relative[1]:
            directions.append((abs(relative[1]), "south" if relative[1] > 0 else "north"))
        contact_direction = None
        if abs(relative[0]) + abs(relative[1]) == 1:
            if relative[0]:
                contact_direction = "east" if relative[0] > 0 else "west"
            else:
                contact_direction = "south" if relative[1] > 0 else "north"
        return {
            "id": "room4_initial_pillar_candidate",
            "live": [8, 21],
            "relative": relative,
            "identity": "established_initial_pillar_candidate",
            "family": "obstacle",
            "direct_distance_reducing_directions": [
                direction for _distance, direction in sorted(directions, reverse=True)
            ],
            "action_readiness": {
                "ready": contact_direction is not None,
                "kind": "interact" if contact_direction else None,
                "direction": contact_direction,
                "instruction": (
                    f"The candidate is directly {contact_direction} of the actor; contact-test with "
                    f"interact({contact_direction}), not movement away from it."
                    if contact_direction else
                    "Approach any cardinally adjacent tile before contact-testing."
                ),
            },
            "status": "identity remains contact-tested until a successful push changes actor and map state",
            "success_evidence": (
                "Actor reaches a cardinally adjacent tile and directed interact produces actor "
                "displacement plus a semantic map-tile change."
            ),
        }

    def _read_bridge_tiles(self, wram: bytes) -> list[int]:
        """Read the three bridge tile values from a WRAM snapshot."""
        values = []
        for x, y in self.BRIDGE_TILES:
            addr = self.tile_address(x, y)
            values.append(wram[addr] if addr < len(wram) else 0xFF)
        return values

    def _bridge_state(self, values: list[int]) -> str:
        """Classify the bridge state from tile values."""
        # Proven from the live Mesen buffer, not inferred from tile appearance.
        if values == [0x00, 0x02, 0x00]:
            return "active"
        if values == [0x02, 0x22, 0x20]:
            return "inactive"
        return "unknown"

    def navigation_target(
        self, observation: Any, mapper: Any, room_context: dict
    ) -> dict | None:
        """Choose the next Room-3 landmark from proven route state.

        Pure distance is wrong here: the south return exit is closer than the
        arrow firing position on the forward leg.  Bridge tiles and the last
        room transition disambiguate the route without prescribing individual
        controller inputs.
        """
        if room_context.get("id") != "room_3":
            return None
        landmarks = {
            item.get("id"): item
            for item in room_context.get("nearby_live_landmarks", [])
        }
        history = mapper.state.get("room_history", []) if mapper is not None else []
        returned_from_room_8 = bool(
            history
            and history[-1].get("from") == "room_8"
            and history[-1].get("to") == "room_3"
        )
        if returned_from_room_8:
            target_id = "return_to_room_2"
            reason = "return leg from room_8"
        else:
            bridge_state = self._bridge_state(self._read_bridge_tiles(observation.wram))
            # The live actor can temporarily obscure one of the sampled map
            # buffer cells while walking across the bridge.  Once the exact
            # Arrow action produced the proven semantic transition, an
            # ``unknown`` sample must not send navigation back to the firing
            # point.  An explicit inactive pattern still wins after a reset.
            bridge_completion = (
                mapper.state.get("completed_landmarks", {}).get(
                    "room_3:arrow_firing_position"
                )
                if mapper is not None
                else None
            )
            # The buffer is a scrolling window, not a fixed world array.  Once
            # the camera anchor shifts, unrelated cells may even reproduce the
            # three-byte inactive pattern by coincidence.  A completion tied
            # to this room instance therefore outranks later raw samples.  A
            # real room reset explicitly expires the resettable completion in
            # OnlineNavigationMapper.record_room_reset().
            bridge_available = bridge_state == "active" or bridge_completion is not None
            if not bridge_available:
                target_id = "arrow_firing_position"
                reason = f"bridge is {bridge_state}; activate it first"
            elif observation.game.x >= 24:
                target_id = "bridge_left_side"
                reason = (
                    "bridge activation was confirmed; cross west"
                    if bridge_state != "active"
                    else "bridge is active; cross west"
                )
            else:
                target_id = "west_door_approach"
                reason = "bridge was crossed; continue to the west door"
        target = landmarks.get(target_id)
        if target is None:
            return None
        return {**target, "selection_reason": reason}

    def on_use_tool(self, before: Any, after: Any) -> str | None:
        before_vals = self._read_bridge_tiles(before.wram)
        after_vals = self._read_bridge_tiles(after.wram)
        before_state = self._bridge_state(before_vals)
        after_state = self._bridge_state(after_vals)

        if before_state != "active" and after_state == "active":
            parts = []
            for (x, y), b, a in zip(self.BRIDGE_TILES, before_vals, after_vals):
                if b != a:
                    parts.append(f"({x},{y}): 0x{b:02X}->0x{a:02X}")
            return f"Bridge activated: {'; '.join(parts)}"

        if before_state == "active" and after_state == "active":
            return "Bridge already active (no tile change)"

        if after_state != "active":
            return f"Bridge not activated (state={after_state}, tiles={after_vals})"

        return None

    def on_reset_room(self, before: Any, after: Any) -> str | None:
        before_vals = self._read_bridge_tiles(before.wram)
        after_vals = self._read_bridge_tiles(after.wram)
        before_state = self._bridge_state(before_vals)
        after_state = self._bridge_state(after_vals)

        if before_state == "active" and after_state != "active":
            return "Room restored to default. The bridge is incomplete again."

        if before_state != "active" and after_state == "active":
            return "Room reset restored the bridge to active."

        return "Room reset: bridge state unchanged."
