"""Real multi-turn test: Nanbeige4.2-3B via llama.cpp — Room-3 bridge sequence."""

from agent.model_client import LocalModelClient
import json

with open("runtime_config.json") as f:
    config = json.load(f)

client = LocalModelClient(config["llm"])

turns = [
    {
        "label": "Turn 1: Agent bei (28,24), blickt West, Brücke aktiv",
        "context": {
            "mode": "exploration",
            "room_id": "room_3",
            "position": {"x": 28, "y": 24},
            "facing": "west",
            "tile_buffer": {"cardinal_cells": {"north": "00", "south": "00", "east": "00", "west": "00"}, "actor_at": "@"},
            "available_actions": ["move", "face", "interact", "look", "wait"],
            "current_room": {
                "objective": "cross the bridge west and reach the door at (17,23)",
                "completed_landmarks": ["room_3:arrow_firing_position"],
                "reference_landmarks": [{"id": "room_3:west_door", "derived_relation": "southwest", "action_readiness": None}],
            },
            "feedback_ledger": [{"action": "use_tool west", "outcome": "bridge_activated", "reward": 1}],
            "reasoning_evidence": ["Bridge tile state changed from hole to floor at (24,26) and (24,28)"],
            "navigation": {"current_room": {"reference_landmarks": []}},
            "dungeon_context": {"nearby_markers": []},
            "strategic_progression": {"accessible": [], "blocked_nearest_requirements": []},
            "episode_summary": {},
        },
    },
    {
        "label": "Turn 2: Agent bei (24,26) auf der Brücke, blickt West",
        "context": {
            "mode": "exploration",
            "room_id": "room_3",
            "position": {"x": 24, "y": 26},
            "facing": "west",
            "tile_buffer": {"cardinal_cells": {"north": "00", "south": "00", "east": "00", "west": "00"}, "actor_at": "@"},
            "available_actions": ["move", "face", "interact", "look", "wait"],
            "current_room": {
                "objective": "cross the bridge west and reach the door at (17,23)",
                "completed_landmarks": ["room_3:arrow_firing_position"],
                "reference_landmarks": [{"id": "room_3:west_door", "derived_relation": "west", "action_readiness": None}],
            },
            "feedback_ledger": [
                {"action": "use_tool west", "outcome": "bridge_activated", "reward": 1},
                {"action": "move west x4", "outcome": "advanced 4 tiles", "reward": 1},
            ],
            "reasoning_evidence": [],
            "navigation": {"current_room": {"reference_landmarks": []}},
            "dungeon_context": {"nearby_markers": []},
            "strategic_progression": {"accessible": [], "blocked_nearest_requirements": []},
            "episode_summary": {},
        },
    },
    {
        "label": "Turn 3: Agent bei (17,23) vor der Westtür, blickt West, Tür in tile_buffer",
        "context": {
            "mode": "exploration",
            "room_id": "room_3",
            "position": {"x": 17, "y": 23},
            "facing": "west",
            "tile_buffer": {"cardinal_cells": {"north": "00", "south": "00", "east": "00", "west": "80"}, "actor_at": "@"},
            "available_actions": ["move", "face", "interact", "look", "wait"],
            "current_room": {
                "objective": "cross the bridge west and reach the door at (17,23)",
                "completed_landmarks": ["room_3:arrow_firing_position"],
                "reference_landmarks": [{"id": "room_3:west_door", "derived_relation": "here", "action_readiness": "interact"}],
            },
            "feedback_ledger": [
                {"action": "use_tool west", "outcome": "bridge_activated", "reward": 1},
                {"action": "move west x4", "outcome": "advanced 4 tiles", "reward": 1},
                {"action": "move west x3", "outcome": "reached west door area", "reward": 1},
            ],
            "reasoning_evidence": ["West cardinal cell shows door tile (0x80)"],
            "navigation": {"current_room": {"reference_landmarks": []}},
            "dungeon_context": {"nearby_markers": []},
            "strategic_progression": {"accessible": [], "blocked_nearest_requirements": []},
            "episode_summary": {},
        },
    },
]

for turn in turns:
    print(f"--- {turn['label']} ---")
    intent = client.choose_intent(turn["context"], max_move_batch=4)
    print(f"  kind={intent.kind}, direction={intent.direction}, count={intent.count}")
    print(f"  rationale={intent.rationale[:130]}")
    print()

print("Multi-turn sequence complete.")