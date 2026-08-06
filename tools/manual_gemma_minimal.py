"""Minimal prompt test for Gemma — how simple must the prompt be?"""

import requests
import json

tests = [
    {
        "label": "Minimal: just choose a direction",
        "messages": [
            {"role": "user", "content": "You are at (28,24) facing west. The bridge is active. Choose: move west, look, or wait. Return only JSON like {\"kind\":\"move\",\"direction\":\"west\",\"count\":1,\"rationale\":\"...\"}"}
        ],
        "max_tokens": 320,
    },
    {
        "label": "Minimal: with position and objective",
        "messages": [
            {"role": "user", "content": "Position (28,24), facing west. Objective: cross bridge to door at (17,23). What do you do? Return JSON {\"kind\":\"move\",\"direction\":\"west\",\"count\":1,\"rationale\":\"...\"}"}
        ],
        "max_tokens": 320,
    },
    {
        "label": "Medium: with feedback context",
        "messages": [
            {"role": "user", "content": "You crossed a bridge by shooting an arrow. Now at (24,26) facing west. The west door is at (17,23). Move west to reach it. Return JSON {\"kind\":\"move\",\"direction\":\"west\",\"count\":4,\"rationale\":\"...\"}"}
        ],
        "max_tokens": 320,
    },
]

for test in tests:
    resp = requests.post(
        "http://127.0.0.1:8080/v1/chat/completions",
        json={
            "model": "gemma",
            "messages": test["messages"],
            "max_tokens": test["max_tokens"],
            "temperature": 0.1,
        },
        timeout=30,
    )
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    print(f"=== {test['label']} ===")
    print(f"  finish={data['choices'][0].get('finish_reason')}, len={len(content)}")
    print(f"  content={repr(content[:250])}")
    print()