"""Manual intent parsing tests for the strict format."""

from agent.intent import Intent

# Test 1: classic kind
i1 = Intent.from_dict({"kind": "move", "direction": "west", "count": 2})
assert i1.kind == "move" and i1.direction == "west" and i1.count == 2
print("PASS: kind=move")

# Test 2: face
i2 = Intent.from_dict({"kind": "face", "direction": "east"})
assert i2.kind == "face" and i2.direction == "east"
print("PASS: kind=face")

# Test 3: use_tool
i3 = Intent.from_dict({"kind": "use_tool", "tool": "arrow"})
assert i3.kind == "use_tool" and i3.tool == "arrow"
print("PASS: kind=use_tool")

# Test 4: look
i4 = Intent.from_dict({"kind": "look", "question": "What blocks progress?"})
assert i4.kind == "look" and i4.question == "What blocks progress?"
print("PASS: kind=look")

# Test 5: count=null
i5 = Intent.from_dict({"kind": "look", "count": None})
assert i5.kind == "look" and i5.count == 1
print("PASS: count=null -> 1")

# Test 6: invalid kind
try:
    Intent.from_dict({"kind": "fly"})
    assert False, "Should have raised"
except ValueError as e:
    assert "fly" in str(e)
    print(f"PASS: rejects invalid kind -> {e}")

# Test 7: missing kind
try:
    Intent.from_dict({"direction": "west"})
    assert False, "Should have raised"
except ValueError as e:
    assert "kind" in str(e)
    print(f"PASS: rejects missing kind -> {e}")

# Test 8: invalid direction
try:
    Intent.from_dict({"kind": "move", "direction": "up"})
    assert False, "Should have raised"
except ValueError as e:
    assert "north" in str(e) or "south" in str(e) or "east" in str(e) or "west" in str(e)
    print(f"PASS: rejects invalid direction -> {e}")

print("All 8 intent-parsing tests passed.")
