"""Validated configuration for the Mesen-only runtime."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "runtime_config.json"


def load_config(path: Path = CONFIG_PATH) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("emulator", {}).get("backend") != "mesen_lua":
        raise ValueError("Only emulator.backend=mesen_lua is supported by the active runtime.")
    limits = config.get("limits", {})
    for key in ("max_actions_per_run", "max_minutes_per_run", "max_move_batch"):
        if float(limits.get(key, 0)) <= 0:
            raise ValueError(f"limits.{key} must be positive")
    llm = config.get("llm", {})
    if float(llm.get("max_thinking_seconds", 270)) > 295:
        raise ValueError("llm.max_thinking_seconds must stay below five minutes")
    if float(llm.get("timeout_seconds", 285)) > 295:
        raise ValueError("llm.timeout_seconds must stay below five minutes")
    if int(llm.get("max_prompt_chars", 0)) <= 0:
        raise ValueError("llm.max_prompt_chars must be positive")
    if not isinstance(config.get("battle", {}).get("execution_enabled", False), bool):
        raise ValueError("battle.execution_enabled must be true or false")
    evolution = config.get("harness_evolution", {})
    if not isinstance(evolution.get("enabled", False), bool):
        raise ValueError("harness_evolution.enabled must be true or false")
    if evolution.get("enabled") and evolution.get("mode", "shadow") not in {"shadow", "gated"}:
        raise ValueError("harness_evolution.mode must be shadow or gated")
    for key in (
        "min_window_actions", "max_window_actions", "max_journal_events", "max_evidence_chars",
        "cooldown_actions", "max_proposals_per_area", "promotion_confirmations",
        "promotion_distinct_runs", "rollback_min_exposures",
        "rollback_consecutive_failures", "max_subagents_per_trigger",
        "subagent_max_turns",
        "max_active_per_area",
    ):
        if key in evolution and int(evolution[key]) <= 0:
            raise ValueError(f"harness_evolution.{key} must be positive")
    return config
