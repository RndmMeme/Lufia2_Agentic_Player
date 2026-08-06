"""Test llama.cpp response_format with JSON schema."""

import requests
import json

# Test 1: json_object type
resp = requests.post(
    "http://127.0.0.1:8080/v1/chat/completions",
    json={
        "model": "gemma",
        "messages": [
            {"role": "user", "content": "Choose: move west or look. Return JSON with kind and direction."}
        ],
        "max_tokens": 256,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    },
    timeout=30,
)
data = resp.json()
print("=== json_object ===")
print("Status:", resp.status_code)
print("Content:", repr(data["choices"][0]["message"]["content"][:300]))
print("Finish:", data["choices"][0].get("finish_reason"))
print()

# Test 2: json_schema type
resp2 = requests.post(
    "http://127.0.0.1:8080/v1/chat/completions",
    json={
        "model": "gemma",
        "messages": [
            {"role": "user", "content": "Choose: move west or look. Return JSON."}
        ],
        "max_tokens": 256,
        "temperature": 0.1,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "intent",
                "schema": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["move", "look", "wait"]},
                        "direction": {"type": ["string", "null"], "enum": ["north", "south", "east", "west", None]},
                        "count": {"type": "integer", "minimum": 1, "maximum": 4},
                        "rationale": {"type": "string"},
                    },
                    "required": ["kind", "direction", "count", "rationale"],
                },
            },
        },
    },
    timeout=30,
)
data2 = resp2.json()
print("=== json_schema ===")
print("Status:", resp2.status_code)
print("Content:", repr(data2["choices"][0]["message"]["content"][:300]))
print("Finish:", data2["choices"][0].get("finish_reason"))
