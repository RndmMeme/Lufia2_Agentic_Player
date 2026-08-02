"""Frame-bounded Mesen controller with WRAM verification."""

from __future__ import annotations

import time
from dataclasses import dataclass

from agent.game_state import GameState
from agent.navigation.online_mapper import LiveNavigationObservation
from wram_discovery.mesen_bridge import MesenFileBridge


BUTTON_FOR_DIRECTION = {"north": "up", "south": "down", "west": "left", "east": "right"}
DIRECTION_CODE = {"south": 0x00, "west": 0x02, "north": 0x04, "east": 0x06}
TOOL_FOCUS = {"hook": 0xA7, "bomb": 0xA8, "arrow": 0xA9, "fire_arrow": 0xAA, "hammer": 0xAB}


@dataclass(frozen=True)
class Observation:
    wram: bytes
    game: GameState
    navigation: LiveNavigationObservation


class MesenController:
    def __init__(self, config: dict):
        self.config = config
        self.bridge = MesenFileBridge(timeout=10.0)

    def connect(self) -> dict:
        self.bridge.start()
        if not self.bridge.wait_attached(timeout=3.0):
            raise TimeoutError("Mesen Lua bridge is not responding")
        info = self.bridge.ping()
        expected = str(self.config.get("rom_sha1", "")).upper()
        if expected and info.get("rom_sha1", "").upper() != expected:
            raise RuntimeError(
                f"Unexpected ROM SHA-1 {info.get('rom_sha1')}; expected {expected}"
            )
        required_protocol = int(self.config.get("bridge_protocol", 1))
        if int(info.get("protocol_version", 1)) < required_protocol:
            raise RuntimeError(
                f"Mesen Lua bridge protocol {info.get('protocol_version', 1)} is stale; "
                f"reload the script for protocol {required_protocol}"
            )
        return info

    def observe(self) -> Observation:
        wram = self.bridge.dump()
        return Observation(wram, GameState.from_wram(wram), LiveNavigationObservation.from_wram(wram))

    def observe_stable(self, timeout: float = 2.0) -> Observation:
        deadline = time.monotonic() + timeout
        previous = None
        stable_reads = 0
        latest = self.observe()
        while time.monotonic() < deadline:
            latest = self.observe()
            nav = latest.navigation
            signature = (nav.map_id, nav.x, nav.y, nav.movement_state, nav.battle_mode)
            if latest.game.in_battle:
                return latest
            if signature == previous and not nav.moving:
                stable_reads += 1
                if stable_reads >= 1:
                    return latest
            else:
                stable_reads = 0
            previous = signature
            time.sleep(0.04)
        return latest

    def pulse(self, button: str) -> Observation:
        self.bridge.pulse(
            button,
            frames=int(self.config.get("pulse_frames", 1)),
            settle_seconds=float(self.config.get("settle_seconds", 0.18)),
        )
        return self.observe_stable()

    def chord(self, held_button: str, pressed_button: str = "a") -> Observation:
        self.bridge.chord(
            held_button,
            pressed_button,
            lead_frames=int(self.config.get("chord_lead_frames", 2)),
            press_frames=int(self.config.get("chord_press_frames", 2)),
            settle_seconds=float(self.config.get("settle_seconds", 0.32)),
        )
        return self.observe_stable()

    def move(self, direction: str, tiles: int | None = None) -> Observation:
        if tiles is None:
            frames = int(self.config.get("exploration_hold_frames", 12))
        else:
            frames_per_tile = int(self.config.get("exploration_frames_per_tile", 6))
            if frames_per_tile < 1:
                raise ValueError("exploration_frames_per_tile must be positive")
            # Protocol v2 deliberately caps one humanoid hold at 30 frames.
            # Keep this validation beside the conversion so the controller can
            # never advertise a distance which the Lua bridge will reject.
            max_tiles = 30 // frames_per_tile
            if not 1 <= int(tiles) <= max_tiles:
                raise ValueError(
                    f"Exploration move tiles must be between 1 and {max_tiles} "
                    f"at {frames_per_tile} frames per tile"
                )
            frames = frames_per_tile * int(tiles)
        self.bridge.pulse(
            BUTTON_FOR_DIRECTION[direction],
            frames=frames,
            settle_seconds=float(self.config.get("settle_seconds", 0.32)),
        )
        return self.observe_stable()

    def interact(self) -> Observation:
        return self.pulse("a")

    def _wait_exploration_mode(self, expected: int, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.bridge.read(0x09A9, 1)[0] == expected:
                return
            time.sleep(0.05)
        raise TimeoutError(f"Exploration mode did not become 0x{expected:02X}")

    def _wait_field_exploration(self, timeout: float = 5.0) -> None:
        """Wait until room reload clears both the field and battle mode bytes."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            exploration_mode, battle_mode = self.bridge.read(0x09A9, 2)
            if exploration_mode == 0x01 and battle_mode == 0x00:
                return
            time.sleep(0.05)
        raise TimeoutError("Room reload did not reach stable field exploration")

    def _observe_field_stable(self, timeout: float = 6.0) -> Observation:
        """Require consecutive full observations after the reset animation."""
        deadline = time.monotonic() + timeout
        previous = None
        stable_reads = 0
        latest = self.observe()
        while time.monotonic() < deadline:
            latest = self.observe()
            signature = (
                latest.game.map_id,
                latest.game.x,
                latest.game.y,
                latest.game.exploration_mode,
                latest.game.battle_mode,
            )
            if latest.game.exploration_mode == 0x01 and latest.game.battle_mode == 0x00:
                stable_reads = stable_reads + 1 if signature == previous else 1
                if stable_reads >= 2:
                    return latest
            else:
                stable_reads = 0
            previous = signature
            time.sleep(0.05)
        return latest

    def face(self, direction: str) -> Observation:
        """Turn with R+direction while proving the actor did not move."""
        if direction not in BUTTON_FOR_DIRECTION:
            raise ValueError(f"Unknown facing direction: {direction}")
        before = self.observe_stable()
        after = self.chord("r", BUTTON_FOR_DIRECTION[direction])
        if after.navigation.position != before.navigation.position:
            raise RuntimeError("Turn-in-place unexpectedly moved the actor")
        if after.navigation.direction != DIRECTION_CODE[direction]:
            raise RuntimeError(
                f"Turn-in-place did not reach {direction}: 0x{after.navigation.direction:02X}"
            )
        return after

    def select_tool(self, tool: str) -> Observation:
        """Select a named dungeon tool through the radial menu and verify focus."""
        normalized = tool.casefold().replace(" ", "_")
        target = TOOL_FOCUS.get(normalized)
        if target is None:
            raise ValueError(f"Unknown dungeon tool: {tool}")
        before = self.observe_stable()
        if before.game.mode != "exploration" or before.game.exploration_mode != 0x01:
            raise RuntimeError("Dungeon tool selection requires stable field exploration")
        try:
            self.bridge.pulse("select", frames=2, settle_seconds=0.1)
            time.sleep(0.75)  # Let the radial-menu opening animation finish.
            for _ in range(len(TOOL_FOCUS)):
                focus = self.bridge.read(0x0A06, 1)[0]
                if focus == target:
                    break
                self.bridge.pulse("right", frames=2, settle_seconds=0.1)
                time.sleep(0.65)
            else:
                raise RuntimeError(f"Tool {normalized} did not appear in the radial menu")
            if self.bridge.read(0x0A06, 1)[0] != target:
                raise RuntimeError(f"Tool focus verification failed for {normalized}")
            self.bridge.pulse("a", frames=2, settle_seconds=0.1)
            self._wait_exploration_mode(0x01, timeout=3.0)
            after = self.observe_stable()
            if after.game.exploration_mode != 0x01:
                raise RuntimeError("Tool confirmation did not return to the field")
            return after
        except Exception:
            # B is the normal reversible cancel; never confirm an unknown focus.
            self.bridge.pulse("b", frames=2, settle_seconds=0.1)
            time.sleep(0.5)
            raise

    def use_tool(self) -> Observation:
        return self.pulse("y")

    def swing_sword(self) -> Observation:
        return self.pulse("b")

    def reset_room(self) -> tuple[Observation, Observation]:
        before = self.observe_stable()
        if before.game.in_battle or before.game.exploration_mode != 0x01:
            raise RuntimeError("Room reset requires stable field exploration")

        self.bridge.pulse("select", frames=2, settle_seconds=0.1)
        time.sleep(float(self.config.get("reset_menu_open_seconds", 0.75)))
        reset_menu = self.observe_stable()
        if reset_menu.game.exploration_mode not in {0x00, 0x04, 0x05}:
            # Select is the reversible close action for this radial menu.
            self.bridge.pulse("select", frames=2, settle_seconds=0.1)
            raise RuntimeError(
                f"Room reset menu was not confirmed: exploration_mode=0x{reset_menu.game.exploration_mode:02X}"
            )

        self.bridge.pulse("up", frames=2, settle_seconds=0.1)
        time.sleep(float(self.config.get("reset_selection_seconds", 0.65)))
        reset_selected = self.observe_stable()
        if reset_selected.game.exploration_mode not in {0x00, 0x04, 0x05}:
            raise RuntimeError(
                "Hourglass Reset confirmation was not reached: "
                f"mode=0x{reset_selected.game.exploration_mode:02X}"
            )

        # The randomizer's live UI uses a bounded two-stage A confirmation:
        # choose Reset, then confirm execution. Stop early if a ROM variant
        # returns to the field after the first confirmation.
        after = reset_selected
        confirmations = int(self.config.get("reset_confirmation_presses", 2))
        if not 1 <= confirmations <= 2:
            raise ValueError("reset_confirmation_presses must be 1 or 2")
        for _ in range(confirmations):
            self.bridge.pulse("a", frames=2, settle_seconds=0.1)
            time.sleep(float(self.config.get("reset_confirmation_seconds", 0.75)))
            after = self.observe_stable(timeout=3.0)
            if not after.game.in_battle and after.game.exploration_mode == 0x01:
                break
        # A successful reset has a room reload animation. A stable read can
        # legitimately catch mode 00 during that animation, so wait for the
        # verified field mode instead of treating the intermediate frame as a
        # failed confirmation.
        if after.game.in_battle or after.game.exploration_mode != 0x01:
            after = self._observe_field_stable(timeout=6.0)
        if after.game.in_battle or after.game.exploration_mode != 0x01:
            raise RuntimeError(
                "Room reset did not return to exploration: "
                f"field=0x{after.game.exploration_mode:02X}, battle=0x{after.game.battle_mode:02X}"
            )
        if after.game.map_id != before.game.map_id:
            raise RuntimeError("Room reset unexpectedly changed the map ID")
        return before, after

    def screenshot(self) -> bytes:
        return self.bridge.screenshot()

    def finish_battle_results(self) -> Observation:
        """Hold A through variable-length EXP/level result animation."""
        self.bridge.hold_until(
            "a",
            0x09AA,
            0,
            max_frames=int(self.config.get("results_hold_max_frames", 3600)),
        )
        return self.observe_stable(timeout=3.0)

    def attack_battle(self, max_inputs: int) -> tuple[Observation, int, str]:
        """Use default Attack/target selections one human-sized A press at a time."""
        observation = self.observe()
        presses = 0
        while observation.game.in_battle and presses < max_inputs:
            observation = self.pulse("a")
            presses += 1
            if observation.game.in_battle and not observation.game.enemies:
                # Result pages animate; avoid sampling faster than the game can advance.
                time.sleep(0.15)
        reason = "battle_cleared" if not observation.game.in_battle else "battle_input_limit"
        return observation, presses, reason
