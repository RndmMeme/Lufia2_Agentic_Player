"""Conservative decoder for confirmed Lufia II battle WRAM."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agent.game_state import GameState, u16


COMMAND_BASE = 0x1F560
COMMAND_STRIDE = 0x0C
INITIATIVE_BASE = 0x1B8C
INITIATIVE_SLOTS = 11
ACTIVE_ACTION_BASE = 0x1F44E


class BattlePhase(str, Enum):
    NOT_IN_BATTLE = "not_in_battle"
    TARGET_SELECTION = "target_selection"
    EXECUTION = "execution"
    RESULTS = "results"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class InitiativeEntry:
    actor_mask: int
    initiative: int

    @property
    def enemy(self) -> bool:
        return bool(self.actor_mask & 0x80)


@dataclass(frozen=True)
class StoredCommand:
    party_slot: int
    target_mask: int
    command: int
    ability_data: tuple[int, int]
    actor_mask: int


@dataclass(frozen=True)
class ActiveAction:
    actor_mask: int
    target_mask: int
    command: int
    action_id: int

    @property
    def meaningful(self) -> bool:
        return bool(self.actor_mask or self.target_mask or self.command or self.action_id)


@dataclass(frozen=True)
class BattleState:
    game: GameState
    phase: BattlePhase
    ui_token_0b4e: int
    input_mode_1f55e: int
    stored_commands: tuple[StoredCommand, ...]
    initiative: tuple[InitiativeEntry, ...]
    active_action: ActiveAction
    target_index: int
    target_flags: int

    @property
    def input_safe(self) -> bool:
        return self.phase in {
            BattlePhase.TARGET_SELECTION,
            BattlePhase.RESULTS,
        }

    @classmethod
    def from_wram(cls, data: bytes) -> "BattleState":
        game = GameState.from_wram(data)
        commands = []
        for slot in range(4):
            base = COMMAND_BASE + slot * COMMAND_STRIDE
            commands.append(
                StoredCommand(
                    party_slot=slot,
                    target_mask=data[base],
                    command=data[base + 4],
                    ability_data=(data[base + 6], data[base + 7]),
                    actor_mask=data[base + 10],
                )
            )
        initiative = []
        for index in range(INITIATIVE_SLOTS):
            base = INITIATIVE_BASE + index * 3
            actor_mask = data[base]
            value = u16(data, base + 1)
            if actor_mask:
                initiative.append(InitiativeEntry(actor_mask, value))
        active = ActiveAction(
            actor_mask=data[ACTIVE_ACTION_BASE],
            target_mask=data[ACTIVE_ACTION_BASE + 2],
            command=data[ACTIVE_ACTION_BASE + 6],
            action_id=data[ACTIVE_ACTION_BASE + 10],
        )
        ui_token = data[0x0B4E]
        input_mode = data[0x1F55E]
        target_index = data[0x0026]
        target_flags = data[0x0027]
        living_enemies = any(enemy.alive for enemy in game.enemies)
        if not game.in_battle:
            phase = BattlePhase.NOT_IN_BATTLE
        elif game.enemies and not living_enemies:
            # Battle remains active while at least one enemy has HP > 0. The
            # first EXP result page can still use UI token 04; later pages use
            # 29/2A/2B. Active-action/initiative bytes are stale throughout.
            phase = BattlePhase.RESULTS
        elif active.meaningful and active.actor_mask in {entry.actor_mask for entry in initiative}:
            phase = BattlePhase.EXECUTION
        elif target_flags:
            phase = BattlePhase.TARGET_SELECTION
        else:
            # Neither 1F55E nor a blank render prompt uniquely separates the
            # pre-menu from the cursorless character action cross.  The input
            # driver therefore tracks that hierarchy from confirmed actions.
            phase = BattlePhase.UNKNOWN
        return cls(
            game,
            phase,
            ui_token,
            input_mode,
            tuple(commands),
            tuple(initiative),
            active,
            target_index,
            target_flags,
        )
