"""Validation boundary for inert shadow harness proposals."""

from __future__ import annotations

from typing import Any


AREAS = ("prompt_overlay", "memory", "skills", "subagents")
OPERATIONS = {"add", "update", "retire"}
SKILL_ACTIONS = {
    "move", "face", "interact", "sword", "select_tool", "use_tool",
    "look", "look_map", "retrieve",
}
SUBAGENT_TOOLS = {
    "get_context", "look", "look_map", "retrieve", "recommend_intent",
}


class HarnessProposalValidator:
    """Reject executable code, unevidenced claims and unsafe tool expansion."""

    def __init__(self, max_per_area: int = 3) -> None:
        self.max_per_area = max(1, int(max_per_area))

    @staticmethod
    def _common(item: dict[str, Any], evidence_indices: set[int]) -> dict[str, Any]:
        operation = str(item.get("operation", ""))
        if operation not in OPERATIONS:
            raise ValueError(f"unsupported proposal operation: {operation!r}")
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("every proposal needs at least one action index as evidence")
        normalized_evidence = []
        for value in evidence:
            if not isinstance(value, int) or value not in evidence_indices:
                raise ValueError(f"proposal cites unavailable evidence index: {value!r}")
            normalized_evidence.append(value)
        result = {
            "operation": operation,
            "scope": str(item.get("scope", ""))[:160],
            "evidence": sorted(set(normalized_evidence)),
            "expected_benefit": str(item.get("expected_benefit", ""))[:500],
            "rollback_when": str(item.get("rollback_when", ""))[:500],
        }
        if not result["scope"] or not result["expected_benefit"]:
            raise ValueError("proposal scope and expected_benefit are required")
        return result

    def validate(
        self,
        payload: dict[str, Any],
        evidence_indices: set[int],
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("refiner response must be a JSON object")
        result: dict[str, Any] = {
            "analysis": str(payload.get("analysis", ""))[:1200],
        }
        for area in AREAS:
            values = payload.get(area, [])
            if not isinstance(values, list):
                raise ValueError(f"{area} must be a list")
            accepted = []
            for item in values[: self.max_per_area]:
                if not isinstance(item, dict):
                    raise ValueError(f"{area} proposal must be an object")
                common = self._common(item, evidence_indices)
                if area in {"prompt_overlay", "memory"}:
                    content = str(item.get("content", ""))[:2000]
                    if not content:
                        raise ValueError(f"{area} proposal requires content")
                    accepted.append({**common, "content": content})
                elif area == "skills":
                    if item.get("code"):
                        raise ValueError("shadow skills may not contain executable code")
                    steps = item.get("steps", [])
                    if not isinstance(steps, list) or not steps:
                        raise ValueError("skill proposal requires declarative steps")
                    normalized_steps = []
                    for step in steps[:12]:
                        if not isinstance(step, dict):
                            raise ValueError("skill step must be an object")
                        kind = str(step.get("kind", ""))
                        if kind not in SKILL_ACTIONS:
                            raise ValueError(f"skill uses non-allowlisted action: {kind!r}")
                        normalized_steps.append({
                            key: step.get(key)
                            for key in ("kind", "direction", "count", "tool", "query")
                            if step.get(key) is not None
                        })
                    accepted.append({
                        **common,
                        "name": str(item.get("name", "unnamed"))[:100],
                        "steps": normalized_steps,
                        "success_when": str(item.get("success_when", ""))[:500],
                    })
                else:
                    tools = item.get("available_tools", [])
                    if not isinstance(tools, list) or not tools:
                        raise ValueError("subagent proposal requires an available_tools list")
                    unknown = {str(tool) for tool in tools} - SUBAGENT_TOOLS
                    if unknown:
                        raise ValueError(f"subagent requests unsafe tools: {sorted(unknown)}")
                    accepted.append({
                        **common,
                        "name": str(item.get("name", "unnamed"))[:100],
                        "instructions": str(item.get("instructions", ""))[:3000],
                        "available_tools": [str(tool) for tool in tools],
                        "max_turns": min(max(int(item.get("max_turns", 1)), 1), 12),
                        "return_condition": str(item.get("return_condition", ""))[:500],
                    })
            result[area] = accepted
        return result
