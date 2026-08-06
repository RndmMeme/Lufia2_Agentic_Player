"""Static validation for the offline Lufia model qualification contract."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "data" / "benchmarks" / "lufia_agent_contract_v1.json"


class LufiaAgentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.cases = cls.payload["cases"]
        cls.by_id = {case["id"]: case for case in cls.cases}

    def test_ids_are_unique(self) -> None:
        self.assertEqual(len(self.cases), len(self.by_id))

    def test_context_references_resolve(self) -> None:
        for case in self.cases:
            if "context_ref" in case:
                self.assertIn(case["context_ref"], self.by_id)
                self.assertIn("context", self.by_id[case["context_ref"]])

    def test_recorded_frames_exist(self) -> None:
        for case in self.cases:
            if case.get("frame"):
                self.assertTrue((ROOT / case["frame"]).is_file(), case["frame"])

    def test_every_case_has_machine_checkable_acceptance(self) -> None:
        for case in self.cases:
            if case["type"] == "intent":
                self.assertTrue(case.get("accepted_intents"), case["id"])
            elif case["type"] == "vision":
                self.assertTrue(case.get("required_keyword_groups"), case["id"])
            else:
                self.fail(f"Unknown case type in {case['id']}: {case['type']}")


if __name__ == "__main__":
    unittest.main()
