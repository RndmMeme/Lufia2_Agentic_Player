"""Run-independent lifecycle for evidence-backed harness adaptations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AREAS = ("prompt_overlay", "memory", "skills", "subagents")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ContinualHarnessStore:
    """Persist candidates, gated activations, canary metrics and rollbacks."""

    SCHEMA = "lufia2-continual-harness-v1"

    def __init__(self, path: Path, config: dict[str, Any]) -> None:
        self.path = Path(path)
        self.config = dict(config)
        self.mode = str(config.get("mode", "shadow"))
        self.state: dict[str, Any] = {
            "schema": self.SCHEMA,
            "revision": 0,
            "candidates": {},
            "active": {area: [] for area in AREAS},
            "history": [],
        }
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if loaded.get("schema") == self.SCHEMA:
                    self.state.update(loaded)
            except (OSError, json.JSONDecodeError):
                pass
        self.state.setdefault("candidates", {})
        self.state.setdefault("active", {})
        self.state.setdefault("history", [])
        for area in AREAS:
            self.state["active"].setdefault(area, [])

    @staticmethod
    def _identity(area: str, proposal: dict[str, Any]) -> str:
        identity = {
            "area": area,
            "operation": proposal.get("operation"),
            "target_id": proposal.get("target_id"),
            "scope": " ".join(str(proposal.get("scope", "")).lower().split()),
        }
        if area in {"prompt_overlay", "memory"}:
            identity["content"] = " ".join(
                str(proposal.get("content", "")).lower().split()
            )
        elif area == "skills":
            identity.update(
                name=str(proposal.get("name", "")).lower(),
                steps=proposal.get("steps", []),
                success_when=" ".join(
                    str(proposal.get("success_when", "")).lower().split()
                ),
            )
        else:
            identity.update(
                name=str(proposal.get("name", "")).lower(),
                instructions=" ".join(
                    str(proposal.get("instructions", "")).lower().split()
                ),
                available_tools=sorted(proposal.get("available_tools", [])),
                return_condition=" ".join(
                    str(proposal.get("return_condition", "")).lower().split()
                ),
            )
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]

    def _save(self) -> None:
        self.state["revision"] = int(self.state.get("revision", 0)) + 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self.state, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def _activate(self, candidate: dict[str, Any], reason: str) -> bool:
        if candidate["status"] == "active":
            return True
        if candidate.get("proposal", {}).get("operation") not in {"add", "update"}:
            candidate["status"] = "review_required"
            return False
        area = candidate["area"]
        maximum = int(self.config.get("max_active_per_area", 3))
        if len(self.state["active"].get(area, [])) >= maximum:
            candidate["status"] = "eligible"
            candidate["activation_blocked"] = "area_capacity"
            return False
        candidate["status"] = "active"
        candidate["activated_at"] = _now()
        candidate["activation_reason"] = reason
        candidate["canary"] = {
            "exposures": 0,
            "positive": 0,
            "nonpositive": 0,
            "consecutive_nonpositive": 0,
            "reward_sum": 0,
            "last_action_index": 0,
        }
        if candidate["id"] not in self.state["active"][area]:
            self.state["active"][area].append(candidate["id"])
        self.state["history"].append({
            "timestamp": _now(), "event": "activated", "candidate_id": candidate["id"],
            "area": area, "reason": reason,
        })
        return True

    def _apply_eligible(self, candidate: dict[str, Any], reason: str) -> bool:
        operation = candidate.get("proposal", {}).get("operation")
        target_id = candidate.get("proposal", {}).get("target_id")
        if operation == "add":
            return self._activate(candidate, reason)
        target = self.state["candidates"].get(str(target_id), {})
        if target.get("status") != "active":
            candidate["status"] = "review_required"
            candidate["activation_blocked"] = "target_is_not_active"
            return False
        if operation == "update":
            self.rollback(str(target_id), f"superseded_by:{candidate['id']}")
            return self._activate(candidate, reason)
        if operation == "retire":
            self.rollback(str(target_id), f"retired_by_evidence:{candidate['id']}")
            candidate["status"] = "applied_retirement"
            candidate["applied_at"] = _now()
            self.state["history"].append({
                "timestamp": _now(), "event": "retirement_applied",
                "candidate_id": candidate["id"], "target_id": target_id,
            })
            return True
        candidate["status"] = "review_required"
        return False

    def ingest(self, generation: dict[str, Any], run_id: str) -> list[str]:
        """Record valid proposals and activate only independently repeated ones."""
        if generation.get("status") != "proposed_not_applied":
            return []
        promoted: list[str] = []
        changed = False
        for area in AREAS:
            for proposal in generation.get("proposals", {}).get(area, []):
                candidate_id = self._identity(area, proposal)
                candidate = self.state["candidates"].setdefault(candidate_id, {
                    "id": candidate_id,
                    "area": area,
                    "proposal": proposal,
                    "status": "candidate",
                    "created_at": _now(),
                    "updated_at": _now(),
                    "sightings": [],
                    "runs": [],
                })
                sighting_key = (
                    str(run_id), int(generation.get("generation", 0)),
                    tuple(proposal.get("evidence", [])),
                )
                existing = {
                    (item.get("run_id"), item.get("generation"), tuple(item.get("evidence", [])))
                    for item in candidate.get("sightings", [])
                }
                if sighting_key in existing:
                    continue
                candidate["sightings"].append({
                    "timestamp": generation.get("timestamp") or _now(),
                    "run_id": str(run_id),
                    "generation": int(generation.get("generation", 0)),
                    "trigger": generation.get("trigger"),
                    "action_index_range": generation.get("action_index_range"),
                    "evidence": proposal.get("evidence", []),
                })
                candidate["runs"] = sorted(set(candidate.get("runs", [])) | {str(run_id)})
                candidate["updated_at"] = _now()
                changed = True
                enough_sightings = len(candidate["sightings"]) >= int(
                    self.config.get("promotion_confirmations", 2)
                )
                enough_runs = len(candidate["runs"]) >= int(
                    self.config.get("promotion_distinct_runs", 2)
                )
                if enough_sightings and enough_runs and candidate["status"] == "candidate":
                    candidate["status"] = "eligible"
                    self.state["history"].append({
                        "timestamp": _now(), "event": "eligible",
                        "candidate_id": candidate_id, "area": area,
                    })
                if self.mode == "gated" and candidate["status"] == "eligible":
                    if self._apply_eligible(candidate, "independent_repetition_gate"):
                        promoted.append(candidate_id)
        if changed or promoted:
            self.state["history"] = self.state["history"][-500:]
            self._save()
        return promoted

    def promote(self, candidate_id: str, reason: str = "manual_review") -> None:
        candidate = self.state["candidates"].get(candidate_id)
        if not candidate:
            raise KeyError(f"unknown harness candidate: {candidate_id}")
        if candidate.get("status") in {"retired", "rolled_back", "applied_retirement"}:
            raise ValueError(f"candidate is not promotable: {candidate.get('status')}")
        if not self._apply_eligible(candidate, reason):
            raise ValueError("candidate cannot be activated automatically; inspect operation/capacity")
        self._save()

    def rollback(self, candidate_id: str, reason: str) -> None:
        candidate = self.state["candidates"].get(candidate_id)
        if not candidate or candidate.get("status") != "active":
            return
        area = candidate["area"]
        candidate["status"] = "rolled_back"
        candidate["rolled_back_at"] = _now()
        candidate["rollback_reason"] = reason
        self.state["active"][area] = [
            value for value in self.state["active"][area] if value != candidate_id
        ]
        self.state["history"].append({
            "timestamp": _now(), "event": "rolled_back",
            "candidate_id": candidate_id, "area": area, "reason": reason,
        })
        self._save()

    @staticmethod
    def _scope_matches(scope: str, mode: str, map_name: str) -> bool:
        normalized = str(scope).lower()
        if any(token in normalized for token in ("global", "*", "all modes")):
            return True
        if mode and mode.lower() in normalized:
            return True
        return bool(map_name and map_name.lower() in normalized)

    def active_entries(self, mode: str, map_name: str) -> dict[str, list[dict[str, Any]]]:
        result = {area: [] for area in AREAS}
        for area in AREAS:
            for candidate_id in self.state["active"].get(area, []):
                candidate = self.state["candidates"].get(candidate_id, {})
                proposal = candidate.get("proposal", {})
                if candidate.get("status") != "active":
                    continue
                if not self._scope_matches(proposal.get("scope", ""), mode, map_name):
                    continue
                result[area].append({"id": candidate_id, **proposal})
        return result

    def observe_action(self, record: dict[str, Any], exposed_ids: set[str]) -> list[str]:
        """Attribute only the next executed action to entries exposed for it."""
        if not exposed_ids:
            return []
        index = int(record.get("index", 0))
        reward = int(record.get("feedback", {}).get("delta", 0))
        rolled_back: list[str] = []
        changed = False
        for candidate_id in sorted(exposed_ids):
            candidate = self.state["candidates"].get(candidate_id)
            if not candidate or candidate.get("status") != "active":
                continue
            canary = candidate.setdefault("canary", {})
            if index <= int(canary.get("last_action_index", 0)):
                continue
            canary["last_action_index"] = index
            canary["exposures"] = int(canary.get("exposures", 0)) + 1
            canary["reward_sum"] = int(canary.get("reward_sum", 0)) + reward
            if reward > 0:
                canary["positive"] = int(canary.get("positive", 0)) + 1
                canary["consecutive_nonpositive"] = 0
            else:
                canary["nonpositive"] = int(canary.get("nonpositive", 0)) + 1
                canary["consecutive_nonpositive"] = int(
                    canary.get("consecutive_nonpositive", 0)
                ) + 1
            changed = True
            exposures = int(canary["exposures"])
            positive_rate = int(canary.get("positive", 0)) / max(1, exposures)
            if (
                exposures >= int(self.config.get("rollback_min_exposures", 4))
                and int(canary.get("consecutive_nonpositive", 0))
                >= int(self.config.get("rollback_consecutive_failures", 3))
                and positive_rate < float(self.config.get("rollback_min_positive_rate", 0.25))
            ):
                rolled_back.append(candidate_id)
        if changed:
            self._save()
        for candidate_id in rolled_back:
            self.rollback(candidate_id, "canary_underperformed")
        return rolled_back

    def summary(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "revision": self.state.get("revision", 0),
            "candidate_counts": {
                status: sum(
                    1 for item in self.state["candidates"].values()
                    if item.get("status") == status
                )
                for status in (
                    "candidate", "eligible", "active", "review_required",
                    "rolled_back", "retired", "applied_retirement",
                )
            },
            "active": {area: list(values) for area, values in self.state["active"].items()},
        }

    def review_queue(self) -> list[dict[str, Any]]:
        return [
            {
                "id": candidate_id,
                "area": candidate.get("area"),
                "status": candidate.get("status"),
                "scope": candidate.get("proposal", {}).get("scope"),
                "operation": candidate.get("proposal", {}).get("operation"),
                "target_id": candidate.get("proposal", {}).get("target_id"),
                "sightings": len(candidate.get("sightings", [])),
                "distinct_runs": len(candidate.get("runs", [])),
                "expected_benefit": candidate.get("proposal", {}).get("expected_benefit"),
                "canary": candidate.get("canary"),
            }
            for candidate_id, candidate in sorted(
                self.state["candidates"].items(),
                key=lambda item: str(item[1].get("updated_at", "")),
                reverse=True,
            )
        ]

    def refinement_context(self) -> dict[str, Any]:
        """Bounded learned state exposed only to the refiner, never the actor core."""
        active = {area: [] for area in AREAS}
        for area in AREAS:
            for candidate_id in self.state["active"].get(area, [])[:3]:
                candidate = self.state["candidates"].get(candidate_id, {})
                active[area].append({
                    "id": candidate_id,
                    "proposal": candidate.get("proposal", {}),
                    "canary": candidate.get("canary", {}),
                })
        return {
            "mode": self.mode,
            "active": active,
            "rule": "update/retire may target only IDs listed here",
        }
