#!/usr/bin/env python3
"""Run the recorded Lufia agent contract against one resident local model.

This benchmark is strictly offline: it reads curated contexts and recorded PNGs
and never connects to or controls Mesen.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import PROJECT_ROOT, load_config
from agent.model_client import LocalModelClient


DEFAULT_CONTRACT = PROJECT_ROOT / "data" / "benchmarks" / "lufia_agent_contract_v1.json"


def _matches(actual: dict, expected: dict) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def _resolve_context(case: dict, cases_by_id: dict[str, dict]) -> dict:
    if "context" in case:
        return deepcopy(case["context"])
    source = cases_by_id[case["context_ref"]]
    return deepcopy(source["context"])


def _vision_keywords(result: dict, groups: list[list[str]]) -> tuple[bool, list[list[str]]]:
    text = json.dumps(result, ensure_ascii=False).casefold()
    missing = [group for group in groups if not any(word.casefold() in text for word in group)]
    return not missing, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--provider", choices=("auto", "llama_cpp", "ollama", "koboldcpp"))
    parser.add_argument("--model", default="")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--skip-vision", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    contract_path = args.contract.resolve()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    cases = contract["cases"]
    cases_by_id = {case["id"]: case for case in cases}
    selected = [case for case in cases if not args.case_ids or case["id"] in args.case_ids]
    if args.skip_vision:
        selected = [case for case in selected if not case.get("frame") and case["type"] != "vision"]
    if not selected:
        raise SystemExit("No benchmark cases selected")

    model_config = dict(load_config()["llm"])
    if args.provider:
        model_config["provider"] = args.provider
    if args.model:
        model_config["model"] = args.model
        for role in ("planner", "vision", "deliberate", "battle"):
            model_config[f"{role}_model"] = args.model
    client = LocalModelClient(model_config)
    resolved = client.detect(force=True)

    report = {
        "schema": "lufia2-model-contract-report-v1",
        "timestamp": datetime.now().isoformat(),
        "contract": str(contract_path),
        "minimum_pass_rate": float(contract.get("minimum_pass_rate", 0.9)),
        "provider": {key: resolved.get(key) for key in ("name", "base_url", "model", "capabilities")},
        "repeats": max(1, args.repeats),
        "offline_only": True,
        "results": [],
    }

    for repeat in range(max(1, args.repeats)):
        for case in selected:
            started = time.monotonic()
            record = {"case": case["id"], "type": case["type"], "repeat": repeat + 1}
            try:
                context = _resolve_context(case, cases_by_id)
                frame = PROJECT_ROOT / case["frame"] if case.get("frame") else None
                if frame is not None and not frame.exists():
                    raise FileNotFoundError(frame)
                if case["type"] == "intent":
                    intent = client.choose_intent(context, max_move_batch=4, frame=frame)
                    actual = asdict(intent)
                    record["actual"] = actual
                    record["accepted"] = case["accepted_intents"]
                    record["passed"] = any(
                        _matches(actual, expected) for expected in case["accepted_intents"]
                    )
                elif case["type"] == "vision":
                    result = client.look(frame, context, case["question"])
                    passed, missing = _vision_keywords(result, case["required_keyword_groups"])
                    record["actual"] = result
                    record["required_keyword_groups"] = case["required_keyword_groups"]
                    record["missing_keyword_groups"] = missing
                    record["passed"] = passed
                else:
                    raise ValueError(f"Unsupported case type: {case['type']}")
            except Exception as exc:
                record["passed"] = False
                record["error"] = f"{type(exc).__name__}: {exc}"
            record["seconds"] = round(time.monotonic() - started, 3)
            report["results"].append(record)
            status = "PASS" if record["passed"] else "FAIL"
            print(f"{status:4} {case['id']} ({record['seconds']:.3f}s)", flush=True)

    passed = sum(bool(item["passed"]) for item in report["results"])
    total = len(report["results"])
    report["summary"] = {
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total, 4),
        "qualified": passed / total >= report["minimum_pass_rate"],
    }

    output = args.output or (
        PROJECT_ROOT / "data" / "benchmarks" /
        f"lufia_agent_{resolved['name']}_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report: {output}")
    return 0 if report["summary"]["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
