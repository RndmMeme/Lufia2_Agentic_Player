import json
import tempfile
import unittest
from pathlib import Path

from agent.adaptation.global_store import ContinualHarnessStore
from agent.adaptation.manager import ContinualHarnessManager
from agent.context_harness import ContextHarness
from agent.model_client import LocalModelClient, SUBAGENT_FORMAT


def proposal(area="prompt_overlay", content="Try a different proven edge after a loop."):
    common = {
        "operation": "add",
        "scope": "exploration/navigation",
        "evidence": [1],
        "expected_benefit": "Reduce repeated traversal.",
        "rollback_when": "The advice reduces verified progress.",
    }
    if area in {"prompt_overlay", "memory"}:
        return {**common, "content": content}
    if area == "skills":
        return {
            **common,
            "name": "leave_loop",
            "steps": [{"kind": "look_map"}, {"kind": "move", "direction": "north"}],
            "success_when": "live position reaches a previously unseen tile",
        }
    return {
        **common,
        "name": "loop_reviewer",
        "instructions": "Review the latest loop and recommend one reversible alternative.",
        "available_tools": ["get_context", "retrieve", "recommend_intent"],
        "max_turns": 2,
        "return_condition": "one evidence-backed intent is available",
    }


def generation(run_number, item, area="prompt_overlay"):
    return {
        "generation": run_number,
        "timestamp": f"2026-08-11T00:00:0{run_number}+00:00",
        "trigger": "repeated_navigation_loop",
        "action_index_range": [1, 1],
        "status": "proposed_not_applied",
        "proposals": {
            "analysis": "loop",
            "prompt_overlay": [item] if area == "prompt_overlay" else [],
            "memory": [item] if area == "memory" else [],
            "skills": [item] if area == "skills" else [],
            "subagents": [item] if area == "subagents" else [],
        },
    }


class ContinualHarnessStoreTests(unittest.TestCase):
    def config(self, mode="gated"):
        return {
            "mode": mode,
            "promotion_confirmations": 2,
            "promotion_distinct_runs": 2,
            "rollback_min_exposures": 4,
            "rollback_consecutive_failures": 3,
            "rollback_min_positive_rate": 0.25,
            "max_active_per_area": 3,
        }

    def test_gated_activation_requires_two_distinct_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ContinualHarnessStore(Path(folder) / "state.json", self.config())
            item = proposal()
            self.assertEqual([], store.ingest(generation(1, item), "run-a"))
            candidate = next(iter(store.state["candidates"].values()))
            self.assertEqual("candidate", candidate["status"])
            self.assertEqual([], store.ingest(generation(2, item), "run-a"))
            self.assertEqual("candidate", candidate["status"])
            promoted = store.ingest(generation(3, item), "run-b")
            self.assertEqual([candidate["id"]], promoted)
            self.assertEqual("active", candidate["status"])
            self.assertIn(candidate["id"], store.state["active"]["prompt_overlay"])

    def test_shadow_collects_but_never_activates(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ContinualHarnessStore(Path(folder) / "state.json", self.config("shadow"))
            item = proposal()
            store.ingest(generation(1, item), "run-a")
            store.ingest(generation(2, item), "run-b")
            candidate = next(iter(store.state["candidates"].values()))
            self.assertEqual("eligible", candidate["status"])
            self.assertEqual([], store.state["active"]["prompt_overlay"])

    def test_canary_rolls_back_only_after_bounded_bad_exposure(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ContinualHarnessStore(Path(folder) / "state.json", self.config())
            item = proposal()
            store.ingest(generation(1, item), "run-a")
            candidate_id = store.ingest(generation(2, item), "run-b")[0]
            for index in range(1, 4):
                rolled_back = store.observe_action(
                    {"index": index, "feedback": {"delta": 0}}, {candidate_id}
                )
                self.assertEqual([], rolled_back)
            rolled_back = store.observe_action(
                {"index": 4, "feedback": {"delta": -1}}, {candidate_id}
            )
            self.assertEqual([candidate_id], rolled_back)
            self.assertEqual("rolled_back", store.state["candidates"][candidate_id]["status"])

    def test_non_add_operation_requires_review(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ContinualHarnessStore(Path(folder) / "state.json", self.config())
            item = proposal()
            item["operation"] = "retire"
            item["target_id"] = "missing-active-id"
            store.ingest(generation(1, item), "run-a")
            store.ingest(generation(2, item), "run-b")
            candidate = next(iter(store.state["candidates"].values()))
            self.assertEqual("review_required", candidate["status"])
            self.assertEqual([], store.state["active"]["prompt_overlay"])

    def test_repeated_update_supersedes_only_its_active_target(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ContinualHarnessStore(Path(folder) / "state.json", self.config())
            original = proposal(content="Original advice")
            store.ingest(generation(1, original), "run-a")
            target_id = store.ingest(generation(2, original), "run-b")[0]
            updated = proposal(content="Improved advice")
            updated.update(operation="update", target_id=target_id)
            store.ingest(generation(3, updated), "run-c")
            updated_id = store.ingest(generation(4, updated), "run-d")[0]
            self.assertEqual("rolled_back", store.state["candidates"][target_id]["status"])
            self.assertEqual("active", store.state["candidates"][updated_id]["status"])
            self.assertNotIn(target_id, store.state["active"]["prompt_overlay"])

    def test_repeated_retire_removes_target_without_becoming_actor_advice(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ContinualHarnessStore(Path(folder) / "state.json", self.config())
            original = proposal(content="Advice to retire")
            store.ingest(generation(1, original), "run-a")
            target_id = store.ingest(generation(2, original), "run-b")[0]
            retirement = proposal(content="The advice is harmful")
            retirement.update(operation="retire", target_id=target_id)
            store.ingest(generation(3, retirement), "run-c")
            applied_id = store.ingest(generation(4, retirement), "run-d")[0]
            self.assertEqual("rolled_back", store.state["candidates"][target_id]["status"])
            self.assertEqual("applied_retirement", store.state["candidates"][applied_id]["status"])
            self.assertEqual([], store.state["active"]["prompt_overlay"])

    def test_active_context_is_scope_filtered(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ContinualHarnessStore(Path(folder) / "state.json", self.config())
            item = proposal()
            store.ingest(generation(1, item), "run-a")
            store.ingest(generation(2, item), "run-b")
            self.assertEqual(1, len(store.active_entries("exploration", "Secret Skills Cave")["prompt_overlay"]))
            self.assertEqual(0, len(store.active_entries("battle", "Secret Skills Cave")["prompt_overlay"]))


class LearnedContextTests(unittest.TestCase):
    def test_exploration_compaction_preserves_learned_harness(self):
        result = ContextHarness._exploration_context({
            "navigation": {"current_room": {}},
            "established_memory": {},
            "learned_harness": {"authority": "lower", "skills": [{"id": "x"}]},
        })
        self.assertEqual("lower", result["learned_harness"]["authority"])

    def test_shadow_manager_never_exposes_preexisting_active_canary(self):
        class Model:
            config = {"enabled": True}

        class Journal:
            def write(self, *args, **kwargs):
                pass

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = root / "run"
            manager = ContinualHarnessManager(
                {
                    "enabled": True,
                    "mode": "shadow",
                    "global_state_path": "state.json",
                    "promotion_confirmations": 2,
                    "promotion_distinct_runs": 2,
                },
                run_dir,
                Model(),
                Journal(),
                root,
            )
            item = proposal()
            manager.store.ingest(generation(1, item), "run-a")
            manager.store.ingest(generation(2, item), "run-b")
            candidate_id = next(iter(manager.store.state["candidates"]))
            manager.store.promote(candidate_id)
            context = {"game": {"mode": "exploration", "map_name": "Secret Skills Cave"}}
            self.assertNotIn("learned_harness", manager.enrich_context(context))
            manager.mode = "gated"
            self.assertIn("learned_harness", manager.enrich_context(context))


class HarnessSubagentClientTests(unittest.TestCase):
    def test_subagent_is_read_only_and_uses_refiner_role(self):
        client = LocalModelClient({})
        captured = {}
        response = {
            "analysis": "north is the only untested edge",
            "request": None,
            "query": None,
            "recommendation": "test north once",
            "suggested_intent": {
                "kind": "move", "direction": "north", "count": 1, "tool": None,
            },
        }

        def chat(messages, role="planner", response_format=None):
            captured.update(messages=messages, role=role, response_format=response_format)
            return json.dumps(response)

        client._chat = chat
        parsed = client.run_harness_subagent(proposal("subagents"), {"game": {}}, [])
        self.assertEqual(response, parsed)
        self.assertEqual("refiner", captured["role"])
        self.assertIs(SUBAGENT_FORMAT, captured["response_format"])
        self.assertIn("do not control", captured["messages"][0]["content"].lower())

    def test_subagent_advice_discards_fields_unused_by_the_intent_kind(self):
        client = LocalModelClient({})
        response = {
            "analysis": "test north",
            "request": None,
            "query": None,
            "recommendation": "move north once",
            "suggested_intent": {
                "kind": "move", "direction": "north", "count": 1, "tool": "arrow",
            },
        }
        client._chat = lambda *args, **kwargs: json.dumps(response)
        parsed = client.run_harness_subagent(proposal("subagents"), {}, [])
        self.assertIsNone(parsed["suggested_intent"]["tool"])


if __name__ == "__main__":
    unittest.main()
