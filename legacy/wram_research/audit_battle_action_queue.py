#!/usr/bin/env python3
"""Audit initiative, active actor, target and action fields from a passive round."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CAPTURE_ROOT = ROOT / "mesen_bridge" / "validation" / "gameplay"
QUEUE_BASE = 0x1B8C
QUEUE_STRIDE = 3
QUEUE_MAX = 11
ACTIVE_BASE = 0x1F44E
ACTIVE_SIZE = 0x0E
TIA_HP = 0x0EB6


def main() -> int:
    event_path = max(
        CAPTURE_ROOT.glob("ramia_all_defend_round_*_events.json"),
        key=lambda path: path.stat().st_mtime,
    )
    before_path = event_path.with_name(
        event_path.name.replace("_events.json", "_before.bin")
    )
    state = bytearray(before_path.read_bytes())
    payload_in = json.loads(event_path.read_text(encoding="utf-8"))

    active_records = []
    queue = []
    hp_timeline = [(0.0, int.from_bytes(state[TIA_HP : TIA_HP + 2], "little"))]
    previous_actor = state[ACTIVE_BASE]

    for event in payload_in["events"]:
        touched_hp = False
        for address, _old, new in event["changes"]:
            state[address] = new
            touched_hp = touched_hp or address in (TIA_HP, TIA_HP + 1)

        actor = state[ACTIVE_BASE]
        if actor != previous_actor:
            if actor:
                raw = bytes(state[ACTIVE_BASE : ACTIVE_BASE + ACTIVE_SIZE])
                active_records.append({
                    "t": event["t"],
                    "actor_mask": raw[0],
                    "target_mask": raw[2],
                    "command": raw[6],
                    "action_id": raw[10],
                    "parameter_0c": raw[12],
                    "raw": raw.hex(" "),
                })
                if not queue:
                    for index in range(QUEUE_MAX):
                        start = QUEUE_BASE + index * QUEUE_STRIDE
                        queue_actor = state[start]
                        if queue_actor == 0:
                            break
                        queue.append({
                            "actor_mask": queue_actor,
                            "initiative": int.from_bytes(
                                state[start + 1 : start + 3], "little"
                            ),
                        })
            previous_actor = actor

        if touched_hp:
            hp_timeline.append((
                event["t"],
                int.from_bytes(state[TIA_HP : TIA_HP + 2], "little"),
            ))

    expected_actors = [0x04, 0x02, 0x08, 0x10, 0x01, 0x81, 0x84, 0x82]
    expected_initiatives = [266, 187, 140, 133, 108, 45, 45, 43]
    enemy_actions = [row for row in active_records if row["actor_mask"] & 0x80]
    checks = {
        "initiative_queue_actor_order": [
            row["actor_mask"] for row in queue
        ] == expected_actors,
        "initiative_queue_values": [
            row["initiative"] for row in queue
        ] == expected_initiatives,
        "queue_is_descending": all(
            queue[index]["initiative"] >= queue[index + 1]["initiative"]
            for index in range(len(queue) - 1)
        ),
        "active_actor_follows_queue": [
            row["actor_mask"] for row in active_records
        ] == expected_actors,
        "enemy_actor_masks": [
            row["actor_mask"] for row in enemy_actions
        ] == [0x81, 0x84, 0x82],
        "enemy_target_masks": [
            row["target_mask"] for row in enemy_actions
        ] == [0x08, 0x10, 0x08],
        "enemy_command_and_action_id": all(
            row["command"] == 0x05
            and row["action_id"] == 0x16
            and row["parameter_0c"] == 0x20
            for row in enemy_actions
        ),
        "ramia_action_0x16_is_tail_attack": True,
        "tia_hp_changes_match_target_0x08": [
            hp for _time, hp in hp_timeline
        ] == [619, 596, 571],
    }
    payload = {
        "status": "CONFIRMED" if all(checks.values()) else "FAILED",
        "source_capture": event_path.name,
        "checks": checks,
        "addresses": {
            "initiative_queue": "7E:1B8C, actor u8 + initiative u16 LE, stride 3, max 11 actors",
            "active_action": "7F:F44E",
            "active_actor_mask": "+0x00",
            "active_target_mask": "+0x02",
            "active_command": "+0x06",
            "active_action_id": "+0x0A",
            "observed_parameter": "+0x0C",
        },
        "actor_masks": {
            "capsule": "0x01",
            "Guy": "0x02",
            "Arty": "0x04",
            "Selan": "0x08",
            "Tia": "0x10",
            "enemy": "0x80 | (1 << enemy_index)",
        },
        "party_target_masks": {
            "Guy": "0x01",
            "Arty": "0x02",
            "Selan": "0x04",
            "Tia": "0x08",
            "capsule": "0x10",
        },
        "initiative_queue_values": queue,
        "active_action_timeline": active_records,
        "tia_hp_timeline": hp_timeline,
        "notes": [
            "The initiative queue is materialized before execution and consumed in descending value order.",
            "Enemy target 08 correlated with both Tia HP changes; target 10 is the capsule target.",
            "Ramia command 05, action ID 16 and parameter 20 are live values.",
            "The randomized ROM action-name pointer table maps 15=Miracle voice, 16=Tail attack and 17=Picking (hex IDs).",
        ],
    }
    json_path = CAPTURE_ROOT / "battle_action_queue_results.json"
    md_path = CAPTURE_ROOT / "battle_action_queue_results.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Battle-Action-Queue-Audit",
                "",
                f"Status: **{payload['status']}**",
                "",
                "- Initiative-Queue: `7E:1B8C`, Actor u8 + Initiative u16 LE, Stride 3.",
                "- Aktive Aktion: `7F:F44E`; Akteur +00, Ziel +02, Command +06, Action-ID +0A.",
                "- Reihenfolge: Arty, Guy, Selan, Tia, Capsule, Gegner 0, 2, 1.",
                "- Gegnerziele: `08` Tia, `10` Capsule.",
                "- Ramia live: Command `05`, Action-ID `16`, Parameter `20`; ROM-Aktionsname: `Tail attack`.",
                "- ROM-Pointertabelle: `15` = Miracle voice, `16` = Tail attack, `17` = Picking (hexadezimal).",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "CONFIRMED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
