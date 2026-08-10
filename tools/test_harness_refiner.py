import json
import tempfile
import unittest
from pathlib import Path

from agent.adaptation.refiner import ShadowHarnessRefiner
from agent.adaptation.trajectory_window import TrajectoryWindow
from agent.adaptation.validator import HarnessProposalValidator
from agent.model_client import REFINEMENT_FORMAT, LocalModelClient


def outcome(index, before, after, delta=0, **action):
    return {
        "schema": "lufia2-action-outcome-v1",
        "index": index,
        "action": {"kind": "move", **action},
        "before": {"position": list(before), "mode": "exploration"},
        "after": {"position": list(after), "mode": "exploration"},
        "navigation": {},
        "feedback": {"delta": delta, "message": "test"},
    }


class _Journal:
    def __init__(self):
        self.events = []

    def write(self, event, **payload):
        self.events.append((event, payload))


class _Model:
    config = {"enabled": True}

    def __init__(self):
        self.calls = []

    def refine_harness(self, evidence):
        self.calls.append(evidence)
        return {
            "analysis": "The route oscillated.",
            "prompt_overlay": [{
                "operation": "add",
                "scope": "exploration/navigation",
                "content": "After an A-B-A-B loop, choose a different proven edge.",
                "evidence": [1, 2, 3, 4],
                "expected_benefit": "Reduce repeated traversal.",
                "rollback_when": "The rule blocks required backtracking.",
            }],
            "memory": [],
            "skills": [],
            "subagents": [],
        }


class TrajectoryWindowTests(unittest.TestCase):
    def test_detects_repeated_navigation_loop(self):
        records = [
            outcome(1, (1, 1), (2, 1)),
            outcome(2, (2, 1), (1, 1)),
            outcome(3, (1, 1), (2, 1)),
            outcome(4, (2, 1), (1, 1)),
        ]
        self.assertEqual(
            "repeated_navigation_loop", TrajectoryWindow.detect_trigger(records)
        )

    def test_build_is_bounded_and_ignores_malformed_jsonl(self):
        with tempfile.TemporaryDirectory() as folder:
            run_dir = Path(folder)
            path = run_dir / "action_outcomes.jsonl"
            lines = [json.dumps(outcome(i, (i, 1), (i + 1, 1))) for i in range(1, 7)]
            path.write_text("\n".join(["not-json", *lines]) + "\n", encoding="utf-8")
            window = TrajectoryWindow(run_dir, max_actions=4)
            payload = window.build("test")
        self.assertEqual([3, 6], payload["action_index_range"])
        self.assertEqual(4, len(payload["actions"]))


class HarnessProposalValidatorTests(unittest.TestCase):
    def test_rejects_executable_skill_code(self):
        payload = {
            "analysis": "test",
            "prompt_overlay": [],
            "memory": [],
            "skills": [{
                "operation": "add", "scope": "exploration", "evidence": [1],
                "expected_benefit": "test", "rollback_when": "failure",
                "name": "unsafe", "code": "print('no')",
                "steps": [{"kind": "move", "direction": "north"}],
                "success_when": "position changes",
            }],
            "subagents": [],
        }
        with self.assertRaisesRegex(ValueError, "executable code"):
            HarnessProposalValidator().validate(payload, {1})

    def test_rejects_uncited_evidence(self):
        payload = {
            "analysis": "test",
            "prompt_overlay": [{
                "operation": "add", "scope": "exploration", "evidence": [99],
                "expected_benefit": "test", "rollback_when": "failure",
                "content": "candidate",
            }],
            "memory": [], "skills": [], "subagents": [],
        }
        with self.assertRaisesRegex(ValueError, "unavailable evidence"):
            HarnessProposalValidator().validate(payload, {1})

    def test_update_must_target_an_active_learned_candidate(self):
        item = {
            "operation": "update", "target_id": "learned-1", "scope": "exploration",
            "evidence": [1], "expected_benefit": "improve", "rollback_when": "worse",
            "content": "revised advice",
        }
        payload = {
            "analysis": "test", "prompt_overlay": [item], "memory": [],
            "skills": [], "subagents": [],
        }
        with self.assertRaisesRegex(ValueError, "active learned candidate"):
            HarnessProposalValidator().validate(payload, {1}, set())
        accepted = HarnessProposalValidator().validate(payload, {1}, {"learned-1"})
        self.assertEqual("learned-1", accepted["prompt_overlay"][0]["target_id"])

    def test_rejects_area_name_as_scope(self):
        payload = {
            "analysis": "test",
            "prompt_overlay": [{
                "operation": "add", "scope": "overlay", "evidence": [1],
                "expected_benefit": "test", "rollback_when": "failure",
                "content": "candidate",
            }],
            "memory": [], "skills": [], "subagents": [],
        }
        with self.assertRaisesRegex(ValueError, "unsupported proposal scope"):
            HarnessProposalValidator().validate(payload, {1})

    def test_rejects_thinking_gate_bypass(self):
        payload = {
            "analysis": "test",
            "prompt_overlay": [{
                "operation": "add", "scope": "exploration", "evidence": [1],
                "expected_benefit": "test", "rollback_when": "failure",
                "content": "Do not wait for a thinking gate; repeat the action.",
            }],
            "memory": [], "skills": [], "subagents": [],
        }
        with self.assertRaisesRegex(ValueError, "immutable policy"):
            HarnessProposalValidator().validate(payload, {1})

    def test_subagent_tools_are_deduplicated(self):
        payload = {
            "analysis": "test", "prompt_overlay": [], "memory": [], "skills": [],
            "subagents": [{
                "operation": "add", "scope": "exploration/navigation", "evidence": [1],
                "expected_benefit": "review route", "rollback_when": "worse",
                "name": "reviewer", "instructions": "Review the route.",
                "available_tools": ["get_context", "get_context", "retrieve"],
                "max_turns": 2, "return_condition": "one reversible option",
            }],
        }
        accepted = HarnessProposalValidator().validate(payload, {1})
        self.assertEqual(
            ["get_context", "retrieve"],
            accepted["subagents"][0]["available_tools"],
        )


class ShadowHarnessRefinerTests(unittest.TestCase):
    def test_shadow_generation_is_persisted_but_inactive(self):
        with tempfile.TemporaryDirectory() as folder:
            run_dir = Path(folder)
            records = [
                outcome(1, (1, 1), (2, 1)),
                outcome(2, (2, 1), (1, 1)),
                outcome(3, (1, 1), (2, 1)),
                outcome(4, (2, 1), (1, 1)),
            ]
            (run_dir / "action_outcomes.jsonl").write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )
            model = _Model()
            journal = _Journal()
            refiner = ShadowHarnessRefiner(
                {
                    "enabled": True,
                    "mode": "shadow",
                    "min_window_actions": 4,
                    "cooldown_actions": 4,
                },
                run_dir,
                model,
                journal,
            )
            generation = refiner.maybe_refine(4)
            persisted = json.loads(
                (run_dir / "harness_evolution" / "generation_0001.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual("proposed_not_applied", generation["status"])
        self.assertFalse(persisted["active"])
        self.assertEqual("shadow", persisted["mode"])
        self.assertEqual(1, len(model.calls))
        self.assertEqual("harness_refinement_shadow", journal.events[0][0])

    def test_disabled_refiner_never_calls_model(self):
        with tempfile.TemporaryDirectory() as folder:
            run_dir = Path(folder)
            model = _Model()
            refiner = ShadowHarnessRefiner(
                {"enabled": False}, run_dir, model, _Journal()
            )
            self.assertIsNone(refiner.maybe_refine(10, "manual"))
            self.assertEqual([], model.calls)
            self.assertFalse((run_dir / "harness_evolution").exists())


class RefinerModelClientTests(unittest.TestCase):
    def test_refiner_schema_leaves_string_limits_to_the_validator(self):
        def contains_max_length(value):
            if isinstance(value, dict):
                return "maxLength" in value or any(
                    contains_max_length(child) for child in value.values()
                )
            if isinstance(value, list):
                return any(contains_max_length(child) for child in value)
            return False

        self.assertFalse(contains_max_length(REFINEMENT_FORMAT))

    def test_nullable_skill_fields_declare_their_json_types(self):
        step = REFINEMENT_FORMAT["properties"]["skills"]["items"]["properties"]["steps"]["items"]
        self.assertEqual(["string", "null"], step["properties"]["direction"]["type"])
        self.assertEqual(["string", "null"], step["properties"]["tool"]["type"])

    def test_refiner_uses_dedicated_role_and_schema(self):
        client = LocalModelClient({})
        captured = {}
        response = {
            "analysis": "insufficient evidence",
            "prompt_overlay": [], "memory": [], "skills": [], "subagents": [],
        }

        def chat(messages, role="planner", response_format=None):
            captured.update(role=role, response_format=response_format, messages=messages)
            return json.dumps(response)

        client._chat = chat
        self.assertEqual(response, client.refine_harness({"actions": []}))
        self.assertEqual("refiner", captured["role"])
        self.assertIs(REFINEMENT_FORMAT, captured["response_format"])
        self.assertIn("SHADOW", captured["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
