"""Raw Gemma test — bypass chat template entirely."""

import requests
import json

# Test 1: Simple completion, no chat
resp = requests.post(
    "http://127.0.0.1:8080/v1/completions",
    json={
        "model": "gemma",
        "prompt": "The player is at position (28,24) facing west. The bridge is active. The west door is at (17,23). The best action is to move",
        "max_tokens": 100,
        "temperature": 0.7,
    },
    timeout=30,
)
data = resp.json()
print("=== Completion ===")
print("Status:", resp.status_code)
print("Content:", repr(data["choices"][0].get("text", "")[:200]))
print()

# Test 2: Chat with temperature 0.7
resp2 = requests.post(
    "http://127.0.0.1:8080/v1/chat/completions",
    json={
        "model": "gemma",
        "messages": [
            {"role": "user", "content": "Say hello"}
        ],
        "max_tokens": 50,
        "temperature": 0.7,
    },
    timeout=30,
)
data2 = resp2.json()
print("=== Chat temp=0.7 ===")
print("Content:", repr(data2["choices"][0]["message"]["content"][:200]))
print()

# Test 3: Chat with JSON instruction, temp 0.7
resp3 = requests.post(
    "http://127.0.0.1:8080/v1/chat/completions",
    json={
        "model": "gemma",
        "messages": [
            {"role": "user", "content": "What is 2+2? Answer with just the number."}
        ],
        "max_tokens": 50,
        "temperature": 0.7,
    },
    timeout=30,
)
data3 = resp3.json()
print("=== Chat 2+2 temp=0.7 ===")
print("Content:", repr(data3["choices"][0]["message"]["content"][:200]))