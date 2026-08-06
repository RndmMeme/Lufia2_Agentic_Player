"""Quick Gemma API test — bypasses model_client.py entirely."""

import requests
import json

system = (
    "You are the bounded decision layer for a Lufia II randomizer speedrun agent. "
    "Return JSON only. Choose one reversible intent. Never invent memory values. "
    "Valid kinds: move, face, interact, sword, select_tool, use_tool, look, look_map, "
    "reset_room, wait, retrieve. If mode is battle, choose battle_attack unless evidence "
    "requires fleeing. Use face to turn without walking. select_tool requires "
    "tool=hook|bomb|arrow|fire_arrow|hammer; use_tool presses Y; sword presses B; "
    "interact presses A. Never choose face when already facing that direction. "
    "Keep rationale short."
)
user = {
    "state_and_goal": {
        "mode": "exploration",
        "room_id": "room_3",
        "position": {"x": 28, "y": 24},
        "facing": "west",
        "current_room": {"objective": "cross the bridge west and reach the door at (17,23)"},
        "feedback_ledger": [{"action": "use_tool west", "outcome": "bridge_activated", "reward": 1}],
    },
    "schema": {
        "kind": "valid kind",
        "direction": "north|south|east|west for move",
        "count": "1..4",
        "rationale": "short",
    },
}

for max_tok in [220, 320, 480, 640]:
    resp = requests.post(
        "http://127.0.0.1:8080/v1/chat/completions",
        json={
            "model": "gemma",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "max_tokens": max_tok,
            "temperature": 0.1,
        },
        timeout=60,
    )
    data = resp.json()
    choice = data["choices"][0]
    content = choice["message"]["content"]
    print(f"=== max_tokens={max_tok} ===")
    print(f"  finish={choice.get('finish_reason')}, len={len(content)}")
    print(f"  content={repr(content[:200])}")
    print()