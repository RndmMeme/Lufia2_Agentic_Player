"""Audit the dungeon actor arrays from controlled Mesen movement captures."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CAPTURE_ROOT = ROOT / "mesen_bridge" / "validation" / "gameplay"
DATA_ROOT = ROOT.parent / "data"

SPRITE_BASE = 0x05D2
MOVEMENT_STATE_BASE = 0x066A
DIRECTION_BASE = 0x0692
X_BASE = 0x06BA
Y_BASE = 0x06E2
MOVEMENT_MODE_BASE = 0x070A
BLOCKED_DIRECTION = 0x1272
FACING_BASE = 0x1E466
ACTOR_COUNT = 0x28


def latest(label: str, suffix: str) -> Path:
    matches = sorted(CAPTURE_ROOT.glob(f"dungeon_player_{label}_*_{suffix}.bin"))
    if not matches:
        raise FileNotFoundError(f"no capture for {label}/{suffix}")
    return matches[-1]


def transition(label: str) -> tuple[bytes, bytes]:
    return latest(label, "before").read_bytes(), latest(label, "after").read_bytes()


def actor(data: bytes, slot: int) -> dict[str, int]:
    return {
        "slot": slot,
        "sprite_id": data[SPRITE_BASE + slot],
        "movement_state": data[MOVEMENT_STATE_BASE + slot],
        "direction": data[DIRECTION_BASE + slot],
        "x": data[X_BASE + slot],
        "y": data[Y_BASE + slot],
        "movement_mode": data[MOVEMENT_MODE_BASE + slot],
        "facing_raw": data[FACING_BASE + slot],
        "facing": data[FACING_BASE + slot] & 0x03,
    }


def main() -> int:
    up_before, up_after = transition("up_free")
    down_before, down_after = transition("down_one_tile")
    right_before, right_after = transition("right_one_tile")
    left_before, left_after = transition("left_one_tile")
    blocked_before, blocked_after = transition("down_blocked")
    collision_before = sorted(
        CAPTURE_ROOT.glob(
            "dungeon_direction_0692_obstacle_1272_down_blocked_*_before.bin"
        )
    )[-1].read_bytes()
    collision_after = sorted(
        CAPTURE_ROOT.glob(
            "dungeon_direction_0692_obstacle_1272_down_blocked_*_after.bin"
        )
    )[-1].read_bytes()
    current = (CAPTURE_ROOT / "dungeon_actor_layout_current.bin").read_bytes()

    movement_data = json.loads(
        (DATA_ROOT / "monster_movement_modes.json").read_text(encoding="utf-8")
    )
    mode_by_sprite = {
        entry["overworld_sprite_id"]: entry["movement_mode"]
        for entry in movement_data["movement_modes_by_overworld_sprite"]
    }
    active = [
        actor(current, slot)
        for slot in range(ACTOR_COUNT)
        if current[SPRITE_BASE + slot] != 0xFF
    ]
    table_backed = [
        row for row in active if 0x80 <= row["sprite_id"] <= 0xEF
    ]

    checks = {
        "up_changes_only_y_negative": (
            up_after[X_BASE] == up_before[X_BASE]
            and up_after[Y_BASE] < up_before[Y_BASE]
        ),
        "down_changes_only_y_positive": (
            down_after[X_BASE] == down_before[X_BASE]
            and down_after[Y_BASE] > down_before[Y_BASE]
        ),
        "right_changes_only_x_positive": (
            right_after[X_BASE] > right_before[X_BASE]
            and right_after[Y_BASE] == right_before[Y_BASE]
        ),
        "left_changes_only_x_negative": (
            left_after[X_BASE] < left_before[X_BASE]
            and left_after[Y_BASE] == left_before[Y_BASE]
        ),
        "blocked_attempt_keeps_coordinates": (
            blocked_after[X_BASE] == blocked_before[X_BASE]
            and blocked_after[Y_BASE] == blocked_before[Y_BASE]
        ),
        "facing_low_bits": (
            (up_after[FACING_BASE] & 3) == 0
            and (down_after[FACING_BASE] & 3) == 1
            and (left_after[FACING_BASE] & 3) == 2
            and (right_after[FACING_BASE] & 3) == 3
        ),
        "movement_state_idle_direction_codes": (
            up_after[MOVEMENT_STATE_BASE] == 4
            and down_after[MOVEMENT_STATE_BASE] == 0
            and left_after[MOVEMENT_STATE_BASE] == 2
            and right_after[MOVEMENT_STATE_BASE] == 6
        ),
        "stable_actor_direction_codes": (
            up_after[DIRECTION_BASE] == 4
            and down_after[DIRECTION_BASE] == 0
            and left_after[DIRECTION_BASE] == 2
            and right_after[DIRECTION_BASE] == 6
        ),
        "blocked_direction_down": (
            collision_before[BLOCKED_DIRECTION] == 0xFF
            and collision_after[BLOCKED_DIRECTION] == 0x01
            and collision_after[X_BASE] == collision_before[X_BASE]
            and collision_after[Y_BASE] == collision_before[Y_BASE]
        ),
        "runtime_modes_match_terrorwave_rom_table": all(
            mode_by_sprite[row["sprite_id"]] == row["movement_mode"]
            for row in table_backed
        ),
        "old_3586_blocked_claim_is_not_supported": (
            blocked_before[0x3586] == 0 and blocked_after[0x3586] == 0
        ),
    }
    payload = {
        "status": "CONFIRMED" if all(checks.values()) else "FAILED",
        "checks": checks,
        "layout": {
            "slot_count": ACTOR_COUNT,
            "empty_sprite": "FF",
            "sprite_id": "7E:05D2 + slot",
            "movement_state": "7E:066A + slot",
            "direction": "7E:0692 + slot",
            "tile_x": "7E:06BA + slot",
            "tile_y": "7E:06E2 + slot",
            "movement_mode": "7E:070A + slot",
            "facing": "7F:E466 + slot, low two bits",
            "last_blocked_direction": "7E:1272; FF means no blocked attempt",
        },
        "movement_state": {
            "bit_0": "movement active",
            "idle": {
                "00": "down",
                "02": "left",
                "04": "up",
                "06": "right",
            },
            "moving": {
                "01": "down",
                "03": "left",
                "05": "up",
                "07": "right",
            },
        },
        "actor_direction": {
            "00": "down",
            "02": "left",
            "04": "up",
            "06": "right",
        },
        "facing": {"00": "up", "01": "down", "02": "left", "03": "right"},
        "blocked_direction": {
            "FF": "clear/no blocked attempt",
            "00": "up",
            "01": "down",
            "02": "left",
            "03": "right",
        },
        "active_actors": active,
        "notes": [
            "Slot 00 is the controlled player actor in this capture.",
            "Sprites 80-EF use Terrorwave MonsterMoveObject indexed by sprite-80.",
            "A blocked down attempt left X/Y unchanged and did not change 7E:3586.",
            "The same blocked attempt changed 7E:1272 from FF to 01.",
        ],
    }
    json_path = CAPTURE_ROOT / "dungeon_actor_layout_results.json"
    md_path = CAPTURE_ROOT / "dungeon_actor_layout_results.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Dungeon-Actor-Layout-Audit",
                "",
                f"Status: **{payload['status']}**",
                "",
                "- 40 Slots (`00`–`27`), Sprite `FF` = leer.",
                "- Sprite: `7E:05D2 + Slot`.",
                "- Tile-X/Y: `7E:06BA/06E2 + Slot`.",
                "- Movement-State: `7E:066A + Slot`; Bit 0 = bewegt sich.",
                "- Stabile Richtung: `7E:0692 + Slot`: 00 Süd, 02 West, 04 Nord, 06 Ost.",
                "- Movement-Modus: `7E:070A + Slot`.",
                "- Blickrichtung: `7F:E466 + Slot`, Bits 0–1.",
                "- Blockierte Richtung: `7E:1272`: FF frei, 00 Nord, 01 Süd, 02 West, 03 Ost.",
                "- Der kontrollierte Wandtest bestätigt `1272`, nicht die alte `3586`-Zuordnung.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "CONFIRMED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
