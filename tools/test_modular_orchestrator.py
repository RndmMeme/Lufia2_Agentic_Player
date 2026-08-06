"""Focused regression tests for the modular orchestrator integration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent.battle_runner import BattleRunner
from agent.context_builder import ContextBuilder, DUNGEON_TOOLS
from agent.context_harness import ModelDriftError, ThinkingGate
from agent.dungeons.secret_skills_cave import SecretSkillsCave
from agent.intent import Intent
from agent.model_client import INTENT_FORMAT, VISION_FORMAT, LocalModelClient
from agent.model_gateway import ModelGateway
from agent.orchestrator import MesenOrchestrator
from agent.watchdog import ModelStallError


class _Response:
    status_code = 200
    text = ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "{}"}}]}


class _Journal:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def write(self, event: str, **details) -> None:
        self.events.append((event, details))


class _Watchdog:
    def run(self, choose, bark):
        bark(31.0)
        return choose(), 1.25


class _Gate:
    @staticmethod
    def fingerprint(context):
        return (context.get("goal"),)

    @staticmethod
    def validate(intent, context, elapsed):
        return None


class _Model:
    @staticmethod
    def choose_intent(context, max_move_batch):
        return Intent("wait", rationale="bounded test")


class _StalledBattle:
    def __init__(self) -> None:
        self.driver = SimpleNamespace(
            last_input_count=0,
            session=SimpleNamespace(stage=SimpleNamespace(value="action_cross")),
        )

    @staticmethod
    def step(observation):
        raise ModelStallError("bounded timeout")


class ModularOrchestratorTests(unittest.TestCase):
    def test_wrong_selected_tool_can_be_replaced(self) -> None:
        builder = ContextBuilder.__new__(ContextBuilder)
        actions = builder._available_actions(None, None, "arrow")
        self.assertIn("select_tool(tool)", actions)
        self.assertIn("use_tool using Y", actions)

    def test_perception_is_once_per_unchanged_state(self) -> None:
        builder = ContextBuilder.__new__(ContextBuilder)
        first = builder._available_actions(None, None, "arrow", [])
        after_look = builder._available_actions(None, None, "arrow", [{"type": "look"}])
        after_both = builder._available_actions(
            None, None, "arrow", [{"type": "look"}, {"type": "look_map"}]
        )
        self.assertIn("look at current frame", first)
        self.assertNotIn("look at current frame", after_look)
        self.assertIn("look_map at current frame plus full curated dungeon map", after_look)
        self.assertNotIn("look at current frame", after_both)
        self.assertNotIn("look_map at current frame plus full curated dungeon map", after_both)

    def test_fully_ready_landmark_advertises_only_required_action(self) -> None:
        actions = [
            "move(direction,count=1..4)",
            "face(direction) using R+direction without moving",
            "use_tool using Y",
            "look at current frame",
        ]
        navigation = {"current_room": {"nearby_live_landmarks": [{
            "id": "arrow_firing_position",
            "action": "use_tool",
            "action_readiness": {
                "completed": False,
                "position_ready": True,
                "facing_ready": True,
                "next_precondition": None,
            },
        }]}}
        self.assertEqual(
            ["use_tool using Y"],
            ContextBuilder._restrict_fully_ready_landmark_action(actions, navigation),
        )

    def test_blocked_direction_requires_causal_failed_move(self) -> None:
        builder = ContextBuilder.__new__(ContextBuilder)
        compact = {"x": 28, "y": 30, "blocked_direction": "north"}
        self.assertIsNone(builder._confirmed_blocked_direction(compact, []))
        failed = [{
            "kind": "move",
            "requested_direction": "north",
            "before": {"position": [28, 30]},
            "after": {"position": [28, 30], "blocked_direction": "north"},
        }]
        self.assertEqual("north", builder._confirmed_blocked_direction(compact, failed))
        moved = [{
            **failed[0],
            "after": {"position": [28, 29], "blocked_direction": "north"},
        }]
        self.assertIsNone(builder._confirmed_blocked_direction(compact, moved))

    def test_face_does_not_erase_confirmed_collision_at_same_position(self) -> None:
        compact = {"x": 21, "y": 26, "blocked_direction": "west"}
        failed = {
            "kind": "move",
            "requested_direction": "west",
            "before": {"position": [21, 26]},
            "after": {"position": [21, 26], "blocked_direction": "west"},
            "navigation_relevant_change": False,
        }
        faced = {
            "kind": "face",
            "requested_direction": "north",
            "before": {"position": [21, 26]},
            "after": {"position": [21, 26], "blocked_direction": "west"},
            "navigation_relevant_change": False,
        }
        self.assertEqual(
            "west",
            ContextBuilder._confirmed_blocked_direction(compact, [failed, faced]),
        )

    def test_non_face_action_ends_collision_carryover(self) -> None:
        compact = {"x": 21, "y": 26, "blocked_direction": "west"}
        failed = {
            "kind": "move",
            "requested_direction": "west",
            "before": {"position": [21, 26]},
            "after": {"position": [21, 26], "blocked_direction": "west"},
            "navigation_relevant_change": False,
        }
        interacted = {
            "kind": "interact",
            "requested_direction": "west",
            "before": {"position": [21, 26]},
            "after": {"position": [21, 26], "blocked_direction": "west"},
            "navigation_relevant_change": False,
        }
        self.assertIsNone(
            ContextBuilder._confirmed_blocked_direction(compact, [failed, interacted])
        )

    def test_spatial_correlation_links_wall_collision_to_target_alternative(self) -> None:
        tile_buffer = {
            "cardinal_cells": [
                {"relative": [-1, 0], "live": [20, 26], "family": "structural_a", "occupied": False},
                {"relative": [0, -1], "live": [21, 25], "family": "plain_floor", "occupied": False},
                {"relative": [0, 1], "live": [21, 27], "family": "structural_a", "occupied": False},
            ],
        }
        result = ContextBuilder._spatial_correlation(
            [21, 26], "west", tile_buffer, {"live": [17, 23]}, {"west": "blocked"}
        )
        self.assertIn("curated map marks this edge blocked", result["conclusion"])
        self.assertTrue(result["map_proves_wall_or_block"])
        self.assertEqual([], result["blocked_edge_tests"])
        self.assertEqual(["west", "north"], result["target_components"])
        alternatives = {item["direction"]: item for item in result["local_alternatives"]}
        self.assertEqual({"north", "south", "east"}, set(alternatives))
        self.assertEqual("plain_floor", alternatives["north"]["tile_family"])
        self.assertTrue(alternatives["north"]["target_aligned"])
        self.assertFalse(alternatives["south"]["target_aligned"])

    def test_spatial_correlation_does_not_infer_wall_without_curated_proof(self) -> None:
        tile_buffer = {
            "cardinal_cells": [
                {"relative": [-1, 0], "live": [20, 26], "family": "structural_a", "occupied": False},
                {"relative": [0, -1], "live": [21, 25], "family": "plain_floor", "occupied": False},
                {"relative": [0, 1], "live": [21, 27], "family": "structural_a", "occupied": False},
            ],
        }
        result = ContextBuilder._spatial_correlation(
            [21, 26], "west", tile_buffer, {"live": [17, 23]}, {"west": "partially_known"}
        )
        self.assertIn("is not wall proof", result["conclusion"])
        self.assertFalse(result["map_proves_wall_or_block"])
        self.assertEqual(3, len(result["blocked_edge_tests"]))

    def test_all_dungeon_tools_have_stable_model_ids(self) -> None:
        self.assertEqual(
            ["hook", "bomb", "arrow", "fire_arrow", "hammer"],
            [tool_id for tool_id, _display_name in DUNGEON_TOOLS],
        )

    def test_secret_cave_bridge_uses_proven_mesen_values(self) -> None:
        cave = SecretSkillsCave(None)
        self.assertEqual("active", cave._bridge_state([0x00, 0x02, 0x00]))
        self.assertEqual("inactive", cave._bridge_state([0x02, 0x22, 0x20]))
        self.assertEqual("unknown", cave._bridge_state([0x00, 0x00, 0x00]))

    def test_secret_cave_room_three_target_follows_bridge_phase(self) -> None:
        cave = SecretSkillsCave(None)
        room = {
            "id": "room_3",
            "nearby_live_landmarks": [
                {"id": "return_to_room_2", "live": [28, 33]},
                {"id": "arrow_firing_position", "live": [28, 24]},
                {"id": "bridge_left_side", "live": [21, 26]},
                {"id": "west_door_approach", "live": [17, 23]},
            ],
        }
        wram = bytearray(0x10000)
        for (x, y), value in zip(cave.BRIDGE_TILES, [0x02, 0x22, 0x20]):
            wram[cave.tile_address(x, y)] = value
        mapper = SimpleNamespace(state={"room_history": []})
        observation = SimpleNamespace(wram=bytes(wram), game=SimpleNamespace(x=28))
        target = cave.navigation_target(observation, mapper, room)
        self.assertEqual("arrow_firing_position", target["id"])

        for (x, y), value in zip(cave.BRIDGE_TILES, [0x00, 0x02, 0x00]):
            wram[cave.tile_address(x, y)] = value
        observation = SimpleNamespace(wram=bytes(wram), game=SimpleNamespace(x=28))
        target = cave.navigation_target(observation, mapper, room)
        self.assertEqual("bridge_left_side", target["id"])

        # Standing on a sampled bridge cell can make the raw three-byte state
        # temporarily unknown.  The proven action-landmark completion keeps
        # the crossing target latched instead of regressing to Arrow.
        mapper.state["completed_landmarks"] = {
            "room_3:arrow_firing_position": {"action": "use_tool"}
        }
        for (x, y), value in zip(cave.BRIDGE_TILES, [0x7F, 0x02, 0x00]):
            wram[cave.tile_address(x, y)] = value
        observation = SimpleNamespace(wram=bytes(wram), game=SimpleNamespace(x=24))
        target = cave.navigation_target(observation, mapper, room)
        self.assertEqual("bridge_left_side", target["id"])

        # The buffer scroll can coincidentally reproduce the inactive byte
        # pattern. Completion remains authoritative until record_room_reset
        # explicitly expires this resettable landmark.
        for (x, y), value in zip(cave.BRIDGE_TILES, [0x02, 0x22, 0x20]):
            wram[cave.tile_address(x, y)] = value
        observation = SimpleNamespace(wram=bytes(wram), game=SimpleNamespace(x=28))
        target = cave.navigation_target(observation, mapper, room)
        self.assertEqual("bridge_left_side", target["id"])

        mapper.state["room_history"] = [{"from": "room_8", "to": "room_3"}]
        target = cave.navigation_target(observation, mapper, room)
        self.assertEqual("return_to_room_2", target["id"])

    def test_watchdog_records_live_action_count(self) -> None:
        journal = _Journal()
        gateway = ModelGateway(_Model(), _Watchdog(), journal, _Gate(), action_count=lambda: 7)
        intent = gateway.ask_intent({"goal": "test"}, 4)
        self.assertEqual("wait", intent.kind)
        bark = next(details for event, details in journal.events if event == "model_watchdog_bark")
        self.assertEqual(7, bark["action"])

    def test_openai_transport_wraps_schema_and_honors_role_budget(self) -> None:
        client = LocalModelClient({"planner_max_tokens": 123, "temperature": 0.0})
        client.detect = lambda force=False: {
            "name": "llama_cpp",
            "base_url": "http://127.0.0.1:8080/v1",
            "model": "test-model",
        }
        with patch("agent.model_client.requests.post", return_value=_Response()) as post:
            client._chat(
                [{"role": "user", "content": "test"}],
                role="planner",
                response_format=INTENT_FORMAT,
            )
        payload = post.call_args.kwargs["json"]
        self.assertEqual(123, payload["max_tokens"])
        self.assertEqual("json_schema", payload["response_format"]["type"])
        self.assertIs(INTENT_FORMAT, payload["response_format"]["json_schema"]["schema"])

    def test_vision_uses_schema_on_openai_transport(self) -> None:
        client = LocalModelClient({"enabled": True})
        client.detect = lambda force=False: {
            "name": "llama_cpp",
            "base_url": "http://127.0.0.1:8080/v1",
            "model": "vision-model",
            "capabilities": ["vision"],
        }
        captured = {}

        def fake_chat(messages, role="planner", response_format=None):
            captured.update(role=role, response_format=response_format)
            return json.dumps({
                "scene_type": "dungeon",
                "relevant_objects": [],
                "navigation_hypothesis": "inspect",
                "confidence": 0.5,
                "safe_next_test": "wait",
            })

        client._chat = fake_chat
        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory) / "frame.png"
            frame.write_bytes(b"png")
            client.look(frame, {}, "What is visible?")
        self.assertEqual("vision", captured["role"])
        self.assertIs(VISION_FORMAT, captured["response_format"])

    def test_intent_frames_are_sent_in_chronological_order(self) -> None:
        client = LocalModelClient({"enabled": True})
        captured = {}

        def fake_chat(messages, role="planner", response_format=None):
            captured.update(messages=messages, role=role, response_format=response_format)
            return json.dumps({
                "kind": "wait", "direction": None, "count": 1,
                "question": None, "query": None, "tool": None,
                "rationale": "inspect frames",
            })

        client._chat = fake_chat
        with tempfile.TemporaryDirectory() as directory:
            older = Path(directory) / "older.png"
            newer = Path(directory) / "newer.png"
            older.write_bytes(b"old")
            newer.write_bytes(b"new")
            client.choose_intent({}, 4, frames=[older, newer])
        content = captured["messages"][1]["content"]
        labels = [part["text"] for part in content if part["type"] == "text"][1:]
        self.assertEqual(["Frame 1/2 (PREVIOUS)", "Frame 2/2 (CURRENT)"], labels)
        self.assertEqual("vision", captured["role"])

    def test_intent_schema_is_restricted_to_advertised_actions(self) -> None:
        client = LocalModelClient({"enabled": True})
        captured = {}

        def fake_chat(messages, role="planner", response_format=None):
            captured["response_format"] = response_format
            return json.dumps({
                "kind": "move", "direction": "north", "count": 1,
                "question": None, "query": None, "tool": None,
                "rationale": "test another edge",
            })

        client._chat = fake_chat
        intent = client.choose_intent({
            "available_actions": [
                "move(direction,count=1..4)",
                "interact(direction optional) using A or direction+A",
            ],
        }, 4)
        self.assertEqual("move", intent.kind)
        self.assertIsNot(INTENT_FORMAT, captured["response_format"])
        self.assertEqual(
            ["move", "interact"],
            captured["response_format"]["properties"]["kind"]["enum"],
        )
        self.assertIn("look", INTENT_FORMAT["properties"]["kind"]["enum"])

    def test_exploration_inventory_retrieval_has_ten_minute_cooldown(self) -> None:
        orchestrator = object.__new__(MesenOrchestrator)
        orchestrator.config = {"llm": {"exploration_inventory_cooldown_seconds": 600}}
        orchestrator.goal = "test"
        orchestrator.last_exploration_inventory_read = None
        orchestrator.knowledge = SimpleNamespace(search=lambda query: [{"text": query}])
        item = SimpleNamespace(name="Potion", quantity=3)
        observation = SimpleNamespace(
            game=SimpleNamespace(mode="exploration", inventory=(item,))
        )
        first = orchestrator._retrieve(observation, "current inventory")
        second = orchestrator._retrieve(observation, "current inventory")
        self.assertEqual("live_wram_inventory", first[0]["type"])
        self.assertEqual([{"name": "Potion", "quantity": 3}], first[0]["items"])
        self.assertEqual("inventory_cooldown", second[0]["type"])

    def test_llama_multimodal_capability_is_accepted_as_vision(self) -> None:
        client = LocalModelClient({"enabled": True})
        client.detect = lambda force=False: {
            "name": "llama_cpp",
            "base_url": "http://127.0.0.1:8080/v1",
            "model": "multimodal-model",
            "capabilities": ["completion", "multimodal"],
        }
        client._chat = lambda *args, **kwargs: json.dumps({
            "scene_type": "dungeon",
            "relevant_objects": [],
            "navigation_hypothesis": "inspect",
            "confidence": 0.5,
            "safe_next_test": "wait",
        })
        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory) / "frame.png"
            frame.write_bytes(b"png")
            result = client.look(frame, {}, "What is visible?")
        self.assertEqual("dungeon", result["scene_type"])

    def test_battle_model_timeout_becomes_controlled_stop(self) -> None:
        journal = _Journal()
        runner = BattleRunner(_StalledBattle(), None, journal, None)
        runner.active = True
        observation = object()
        returned, inputs, stop_reason = runner.step(observation, False, 1, None, 0)
        self.assertIs(observation, returned)
        self.assertEqual(0, inputs)
        self.assertEqual("battle_step_rejected", stop_reason)

    def test_ready_action_landmark_rejects_movement(self) -> None:
        gate = ThinkingGate({"max_thinking_seconds": 120})
        context = {
            "game": {"mode": "exploration", "position": [50, 13]},
            "navigation": {"current_room": {"nearby_live_landmarks": [{
                "id": "switch_south_approach",
                "action": "sword",
                "action_readiness": {
                    "completed": False,
                    "position_ready": True,
                    "facing_ready": True,
                    "next_precondition": None,
                },
            }]}},
            "tile_buffer": {},
        }
        with self.assertRaises(ModelDriftError):
            gate.validate(Intent("move", direction="north"), context, 1.0)
        gate.validate(Intent("sword"), context, 1.0)


if __name__ == "__main__":
    unittest.main()
