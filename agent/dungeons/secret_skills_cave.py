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

    def tile_address(self, x: int, y: int) -> int:
        return self.MAP_BASE + x + y * self.MAP_STRIDE

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
