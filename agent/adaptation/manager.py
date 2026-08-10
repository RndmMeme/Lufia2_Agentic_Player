"""End-to-end coordinator for refinement, activation, advice and rollback."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .global_store import ContinualHarnessStore
from .refiner import ShadowHarnessRefiner


class ContinualHarnessManager:
    def __init__(
        self,
        config: dict,
        run_dir: Path,
        model: Any,
        journal: Any,
        project_root: Path,
    ) -> None:
        self.config = dict(config or {})
        self.enabled = bool(self.config.get("enabled", False))
        self.mode = str(self.config.get("mode", "shadow"))
        self.run_dir = Path(run_dir)
        self.run_id = str(self.run_dir.resolve())
        self.model = model
        self.journal = journal
        configured_path = Path(
            self.config.get("global_state_path", "data/harness/continual_harness.json")
        )
        if not configured_path.is_absolute():
            configured_path = project_root / configured_path
        configured_path = configured_path.resolve()
        project_root = project_root.resolve()
        if configured_path != project_root and project_root not in configured_path.parents:
            raise ValueError("harness_evolution.global_state_path must stay inside the project")
        self.store = (
            ContinualHarnessStore(configured_path, self.config)
            if self.enabled else None
        )
        self.refiner = ShadowHarnessRefiner(
            self.config,
            run_dir,
            model,
            journal,
            global_context=(self.store.refinement_context if self.store else None),
        )
        self.exposed_ids: set[str] = set()

    def maybe_refine(
        self, current_action: int, explicit_reason: str | None = None
    ) -> dict[str, Any] | None:
        generation = self.refiner.maybe_refine(current_action, explicit_reason)
        if generation and self.store:
            try:
                promoted = self.store.ingest(generation, self.run_id)
                if promoted:
                    self.journal.write(
                        "harness_candidates_applied", candidate_ids=promoted,
                        reason="independent_repetition_gate",
                    )
            except Exception as exc:
                self.journal.write(
                    "harness_global_store_failed", operation="ingest",
                    error=str(exc)[:1200],
                )
        return generation

    def enrich_context(self, context: dict[str, Any]) -> dict[str, Any]:
        if not self.store or self.mode != "gated":
            self.exposed_ids = set()
            return context
        game = context.get("game", {})
        entries = self.store.active_entries(
            str(game.get("mode", "")),
            str(game.get("map_name", "") or game.get("zone_name", "")),
        )
        exposed = {
            item["id"] for values in entries.values() for item in values
        }
        self.exposed_ids = exposed
        if not exposed:
            return context
        enriched = dict(context)
        enriched["learned_harness"] = {
            "authority": (
                "gated learned advice; never overrides live WRAM, curated facts, "
                "controller semantics, safety gates, or dungeon reset policy"
            ),
            "prompt_overlays": entries["prompt_overlay"][:3],
            "memories": entries["memory"][:3],
            "skills": entries["skills"][:3],
        }
        return enriched

    def observe_latest_action(self) -> None:
        if not self.store or self.mode != "gated" or not self.exposed_ids:
            return
        records = self.refiner.window.action_records()
        if not records:
            return
        try:
            rolled_back = self.store.observe_action(records[-1], self.exposed_ids)
        except Exception as exc:
            self.journal.write(
                "harness_global_store_failed", operation="observe_action",
                error=str(exc)[:1200],
            )
            self.exposed_ids = set()
            return
        if rolled_back:
            self.journal.write(
                "harness_canary_rollback", candidate_ids=rolled_back,
                action_index=records[-1].get("index"),
            )
        self.exposed_ids = set()

    def subagent_advice(
        self,
        trigger: str,
        context: dict[str, Any],
        read_tools: dict[str, Callable[[str], Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if (
            not self.store
            or self.mode != "gated"
            or not self.model.config.get("enabled", False)
        ):
            return []
        game = context.get("game", {})
        entries = self.store.active_entries(
            str(game.get("mode", "")), str(game.get("map_name", "")),
        )["subagents"]
        results = []
        read_tools = read_tools or {}
        for spec in entries[: int(self.config.get("max_subagents_per_trigger", 1))]:
            evidence = {
                "trigger": trigger,
                "goal": context.get("goal"),
                "game": game,
                "position_update": context.get("position_update"),
                "navigation": context.get("navigation"),
                "recent_agent_actions": context.get("recent_agent_actions", [])[-3:],
                "feedback": context.get("feedback"),
            }
            tool_results = []
            turns = min(
                int(spec.get("max_turns", 1)),
                int(self.config.get("subagent_max_turns", 3)),
            )
            response = None
            try:
                for _ in range(max(1, turns)):
                    response = self.model.run_harness_subagent(spec, evidence, tool_results)
                    request = response.get("request")
                    if (
                        request in {"look", "look_map", "retrieve"}
                        and request in spec.get("available_tools", [])
                        and request in read_tools
                    ):
                        query = str(response.get("query") or context.get("goal") or "")[:300]
                        tool_results.append({
                            "tool": request,
                            "query": query,
                            "result": read_tools[request](query),
                        })
                        continue
                    break
            except Exception as exc:
                self.journal.write(
                    "harness_subagent_failed", subagent_id=spec.get("id"),
                    trigger=trigger, error=str(exc)[:1200],
                )
                continue
            if response:
                result = {
                    "type": "learned_subagent_advice",
                    "subagent_id": spec["id"],
                    "name": spec.get("name"),
                    "trigger": trigger,
                    "analysis": response.get("analysis"),
                    "recommendation": response.get("recommendation"),
                    "suggested_intent": response.get("suggested_intent"),
                    "authority": "advisory only; actor and normal gates decide",
                }
                results.append(result)
                self.journal.write("harness_subagent_advice", **result)
        return results

    def summary(self) -> dict[str, Any]:
        return self.store.summary() if self.store else {"enabled": False}
