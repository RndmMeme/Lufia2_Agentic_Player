"""Bounded, resumable supervision for long autonomous Mesen sessions."""

from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.config import load_config
from agent.game_state import GameState
from agent.mesen_controller import MesenController
from run_agent import CONTROLLER_LOCK_PATH, exclusive_file_lock
from wram_discovery.mesen_bridge import MesenFileBridge


RECOVERABLE_STOPS = {
    "action_limit",
    "time_limit",
    "reasoning_step_limit",
    "unsupported_model_intent",
}
HARD_STOPS = {
    "battle_execution_disabled",
    "battle_model_required",
    "battle_resume_stage_required",
    "battle_step_rejected",
    "needs_model_or_user_review",
}
SUPERVISOR_LOCK_PATH = Path(__file__).resolve().parent.parent / "data" / "runtime" / "long_session.lock"
STOP_REQUEST_PATH = Path(__file__).resolve().parent.parent / "data" / "runtime" / "long_session.stop"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_fingerprint(summary: dict[str, Any]) -> tuple[Any, ...]:
    state = summary.get("state", {})
    navigation = summary.get("navigation", {})
    return (
        state.get("map_id"), state.get("x"), state.get("y"),
        state.get("mode"), state.get("event_flags"), state.get("dungeon_flags"),
        navigation.get("current_room"),
        json.dumps(navigation.get("visited_rooms", []), sort_keys=True),
    )


def classify_stop(reason: str, continue_after_objective: bool = False) -> str:
    if reason == "operator_stop":
        return "operator_stop"
    if reason in RECOVERABLE_STOPS:
        return "resume"
    if reason == "objective_complete":
        return "new_episode" if continue_after_objective else "complete"
    if reason == "objective_map_boundary":
        return "new_episode"
    if reason in HARD_STOPS:
        return "halt"
    return "halt"


class LongSessionSupervisor:
    SCHEMA = "lufia2-long-session-v2"

    def __init__(
        self,
        project_root: Path,
        session_dir: Path,
        goal: str,
        hours: float,
        cycle_minutes: float = 15,
        cycle_actions: int = 400,
        max_unchanged_cycles: int = 4,
        retry_failures: int = 3,
        continue_after_objective: bool = False,
        recovery_mode: str = "slot3",
        recovery_pause_seconds: float = 30,
        python_executable: str = sys.executable,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.session_dir = Path(session_dir).resolve()
        self.goal = goal
        self.hours = float(hours)
        self.cycle_minutes = float(cycle_minutes)
        self.cycle_actions = int(cycle_actions)
        self.max_unchanged_cycles = int(max_unchanged_cycles)
        self.retry_failures = int(retry_failures)
        self.continue_after_objective = bool(continue_after_objective)
        self.recovery_mode = str(recovery_mode)
        self.recovery_pause_seconds = max(1.0, float(recovery_pause_seconds))
        self.python_executable = python_executable
        if self.project_root != self.session_dir and self.project_root not in self.session_dir.parents:
            raise ValueError("session_dir must stay inside the project")
        if self.hours <= 0 or self.cycle_minutes <= 0 or self.cycle_actions <= 0:
            raise ValueError("hours, cycle_minutes and cycle_actions must be positive")
        if self.max_unchanged_cycles <= 0 or self.retry_failures <= 0:
            raise ValueError("supervisor retry limits must be positive")
        if self.recovery_mode not in {"slot3", "pause"}:
            raise ValueError("recovery_mode must be slot3 or pause")
        self.state_path = self.session_dir / "session_state.json"
        self.log_path = self.session_dir / "supervisor.jsonl"
        self.state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
            if loaded.get("schema") != self.SCHEMA:
                raise ValueError("unsupported long-session state schema")
            return loaded
        return {
            "schema": self.SCHEMA,
            "started_at": utc_now(),
            "status": "created",
            "episode": 1,
            "cycles": 0,
            "unchanged_cycles": 0,
            "consecutive_failures": 0,
            "last_fingerprint": None,
            "last_stop_reason": None,
            "recoveries": 0,
            "recovery_anchor_verified": False,
        }

    def _save(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(self.state, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.state_path)

    def _log(self, event: str, **payload: Any) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"timestamp": utc_now(), "event": event, **payload}, ensure_ascii=False) + "\n")

    def _episode_dir(self) -> Path:
        return self.session_dir / "episodes" / f"episode_{int(self.state['episode']):04d}"

    def _command(self, resume: bool) -> list[str]:
        command = [
            self.python_executable,
            str(self.project_root / "run_agent.py"),
            "--execute", "--enable-llm", "--enable-battle", "--enable-harness-gated",
            "--max-actions", str(self.cycle_actions),
            "--max-minutes", str(self.cycle_minutes),
            "--run-dir", str(self._episode_dir()),
            "--goal", self.goal,
            "--stop-file", str(STOP_REQUEST_PATH),
        ]
        if resume:
            command.append("--resume-run")
        return command

    def _verify_recovery_anchor(self) -> None:
        if self.recovery_mode != "slot3":
            return
        with exclusive_file_lock(CONTROLLER_LOCK_PATH, "Mesen controller is already locked"):
            bridge = MesenFileBridge(timeout=10.0)
            bridge.start()
            if not bridge.wait_attached(timeout=3.0):
                raise TimeoutError("Mesen Lua bridge is not responding for recovery verification")
            info = bridge.ping()
            if int(info.get("protocol_version", 1)) < 4:
                raise RuntimeError("Mesen Lua bridge protocol 4 is required for read-only slot 3 recovery")
            anchor = bridge.recovery_anchor_info()
        if self.state.get("recovery_anchor_verified"):
            if (
                str(anchor["path"]) != str(self.state.get("recovery_anchor_path"))
                or int(anchor["anchor_bytes"]) != int(self.state.get("recovery_anchor_bytes") or 0)
            ):
                raise RuntimeError("Slot 3 recovery anchor identity changed for an existing session")
            self._assert_recovery_anchor_unchanged()
            self._log("recovery_anchor_reverified", policy="read_only_slot_3")
            return
        anchor_path = Path(anchor["path"])
        anchor_digest = hashlib.sha256(anchor_path.read_bytes()).hexdigest()
        self.state["recovery_anchor_verified"] = True
        self.state["recovery_anchor_path"] = anchor["path"]
        self.state["recovery_anchor_bytes"] = anchor["anchor_bytes"]
        self.state["recovery_anchor_sha256"] = anchor_digest
        self._save()
        self._log(
            "recovery_anchor_verified",
            path=anchor["path"],
            bytes=anchor["anchor_bytes"],
            sha256=anchor_digest,
            policy="read_only_slot_3",
        )

    def _assert_recovery_anchor_unchanged(self) -> None:
        path = Path(str(self.state.get("recovery_anchor_path", "")))
        expected_size = int(self.state.get("recovery_anchor_bytes") or 0)
        expected_digest = str(self.state.get("recovery_anchor_sha256") or "")
        if not path.is_file() or expected_size <= 0 or not expected_digest:
            raise RuntimeError("Verified slot 3 recovery anchor metadata is missing")
        data = path.read_bytes()
        if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_digest:
            raise RuntimeError("Slot 3 recovery anchor changed during the long session")

    @staticmethod
    def _room_reset_ticket(episode_dir: Path) -> bool:
        path = episode_dir / "short_term_memory.json"
        if not path.exists():
            return False
        try:
            memory = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return bool(memory.get("room_reset_recovery", {}).get("eligible"))

    @staticmethod
    def _movement_loop_ticket(episode_dir: Path) -> bool:
        """Detect a local navigation loop without treating exploration as failure."""
        path = episode_dir / "short_term_memory.json"
        if not path.exists():
            return False
        try:
            memory = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        actions = list(memory.get("recent_actions", []))[-12:]
        if len(actions) < 8:
            return False
        if any(
            int(action.get("semantic_tile_changes") or 0) > 0
            or action.get("completed_checkpoint")
            or action.get("completed_landmark")
            for action in actions
        ):
            return False
        movements = [
            action for action in actions
            if action.get("kind") in {"move", "interact"}
            and isinstance(action.get("from"), list)
            and isinstance(action.get("to"), list)
        ]
        if len(movements) < 8:
            return False
        positions = {
            tuple(position)
            for action in movements
            for position in (action.get("from"), action.get("to"))
            if isinstance(position, list) and len(position) == 2
        }
        edges = Counter(
            tuple(sorted((tuple(action["from"]), tuple(action["to"]))))
            for action in movements
            if action["from"] != action["to"]
        )
        blocked = Counter(
            (tuple(action["from"]), action.get("direction"))
            for action in movements
            if action["from"] == action["to"] or action.get("blocked_direction")
        )
        negative = sum(int(action.get("reward") or 0) <= -2 for action in movements)
        repeated_edge = bool(edges) and max(edges.values()) >= 6
        repeated_block = bool(blocked) and max(blocked.values()) >= 4
        return repeated_block or (
            len(positions) <= 3 and negative >= 6 and repeated_edge
        )

    @staticmethod
    def _game_fingerprint(wram: bytes) -> dict[str, Any]:
        game = GameState.from_wram(wram)
        return {
            "map_id": game.map_id,
            "x": game.x,
            "y": game.y,
            "mode": game.mode,
            "event_flags": game.event_flags,
            "dungeon_flags": game.dungeon_flags,
        }

    def _wait_for_recovery_anchor(self, bridge: MesenFileBridge, timeout: float = 12.0) -> None:
        deadline = time.monotonic() + timeout
        previous = None
        stable_reads = 0
        while time.monotonic() < deadline:
            latest = self._game_fingerprint(bridge.dump())
            if latest == previous:
                stable_reads += 1
            else:
                stable_reads = 0
                previous = latest
            if stable_reads >= 2:
                expected = self.state.get("recovery_anchor_fingerprint")
                if isinstance(expected, dict) and expected and latest != expected:
                    raise RuntimeError(
                        "Slot 3 load produced a different WRAM fingerprint than the first verified load"
                    )
                if not expected:
                    self.state["recovery_anchor_fingerprint"] = latest
                    self._save()
                    self._log("recovery_anchor_fingerprint_learned", fingerprint=latest)
                return
            time.sleep(0.15)
        raise RuntimeError("Slot 3 load did not settle to a stable WRAM fingerprint")

    def _recover(self, episode_dir: Path) -> str:
        with exclusive_file_lock(CONTROLLER_LOCK_PATH, "Mesen controller is already locked"):
            if self._room_reset_ticket(episode_dir):
                config = load_config(self.project_root / "runtime_config.json")
                controller = MesenController(config["emulator"])
                controller.connect()
                controller.reset_room()
                return "room_reset"
            if self.recovery_mode == "slot3":
                self._assert_recovery_anchor_unchanged()
                bridge = MesenFileBridge(timeout=10.0)
                bridge.start()
                if not bridge.wait_attached(timeout=3.0):
                    raise TimeoutError("Mesen Lua bridge is not responding for slot 3 recovery")
                bridge.load_recovery_anchor()
                self._wait_for_recovery_anchor(bridge)
                return "slot3_recovery_anchor"
        time.sleep(self.recovery_pause_seconds)
        return "pause"

    def _recover_episode(self, cycle: int, episode_dir: Path, cause: str) -> str:
        try:
            recovery = self._recover(episode_dir)
        except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
            recovery = "recovery_failed"
            self._log("recovery_failed", cycle=cycle, cause=cause, error=str(exc)[:1200])
            time.sleep(self.recovery_pause_seconds)
        self.state["recoveries"] = int(self.state.get("recoveries", 0)) + 1
        self.state["episode"] = int(self.state["episode"]) + 1
        self.state["unchanged_cycles"] = 0
        self.state["last_fingerprint"] = None
        self.state["last_recovery"] = recovery
        self.state["last_recovery_cause"] = cause
        self.state["last_recovery_at"] = utc_now()
        self._save()
        self._log(
            "episode_recovered", cycle=cycle, cause=cause, recovery=recovery,
            next_episode=self.state["episode"],
        )
        return recovery

    def run(self) -> dict[str, Any]:
        deadline = time.monotonic() + self.hours * 3600
        resume = (self._episode_dir() / "summary.json").exists()
        self.state["status"] = "running"
        self._save()
        self._verify_recovery_anchor()
        while time.monotonic() < deadline:
            episode_dir = self._episode_dir()
            episode_dir.mkdir(parents=True, exist_ok=True)
            cycle = int(self.state["cycles"]) + 1
            output_path = self.session_dir / f"cycle_{cycle:05d}.log"
            command = self._command(resume)
            self._log("cycle_started", cycle=cycle, episode=self.state["episode"], resume=resume)
            with output_path.open("w", encoding="utf-8") as output:
                process = subprocess.Popen(
                    command,
                    cwd=self.project_root,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
                )
                self.state["active_child_pid"] = process.pid
                self._save()
                self._log("child_started", cycle=cycle, pid=process.pid)
                try:
                    return_code = process.wait(timeout=self.cycle_minutes * 60 + 360)
                except KeyboardInterrupt:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                    self.state["active_child_pid"] = None
                    self.state["status"] = "interrupted"
                    self.state["cycles"] = cycle
                    self._save()
                    self._log("halted", reason="user_interrupt", cycle=cycle)
                    raise
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                    self.state["active_child_pid"] = None
                    self.state["cycles"] = cycle
                    self._recover_episode(cycle, episode_dir, "child_timeout")
                    resume = False
                    continue

            self.state["active_child_pid"] = None
            self._save()

            self.state["cycles"] = cycle
            summary_path = episode_dir / "summary.json"
            if return_code != 0 or not summary_path.exists():
                self.state["consecutive_failures"] = int(self.state["consecutive_failures"]) + 1
                self._log("cycle_failed", cycle=cycle, return_code=return_code)
                if int(self.state["consecutive_failures"]) >= self.retry_failures:
                    self.state["status"] = "waiting_external_dependency"
                    self._save()
                    time.sleep(self.recovery_pause_seconds)
                    self.state["consecutive_failures"] = 0
                    continue
                self._save()
                time.sleep(min(30, 5 * int(self.state["consecutive_failures"])))
                resume = summary_path.exists()
                continue

            self.state["consecutive_failures"] = 0
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            reason = str(summary.get("stop_reason", "unknown"))
            fingerprint = list(state_fingerprint(summary))
            if fingerprint == self.state.get("last_fingerprint"):
                self.state["unchanged_cycles"] = int(self.state["unchanged_cycles"]) + 1
            else:
                self.state["unchanged_cycles"] = 0
            self.state["last_fingerprint"] = fingerprint
            self.state["last_stop_reason"] = reason
            decision = classify_stop(reason, self.continue_after_objective)
            movement_loop = self._movement_loop_ticket(episode_dir)
            self._log(
                "cycle_finished", cycle=cycle, episode=self.state["episode"],
                stop_reason=reason, decision=decision,
                unchanged_cycles=self.state["unchanged_cycles"],
                movement_loop=movement_loop,
            )

            if decision == "operator_stop":
                self.state["status"] = "operator_stopped"
                self._save()
                self._log("session_finished", reason="operator_stop")
                return self.state
            if movement_loop or int(self.state["unchanged_cycles"]) >= self.max_unchanged_cycles:
                cause = "movement_loop" if movement_loop else "unchanged_cycles"
                self._recover_episode(cycle, episode_dir, cause)
                resume = False
                continue
            if decision == "resume":
                resume = True
                self._save()
                continue
            if decision == "new_episode":
                self.state["episode"] = int(self.state["episode"]) + 1
                self.state["unchanged_cycles"] = 0
                self.state["last_fingerprint"] = None
                resume = False
                self._save()
                continue
            if decision == "complete":
                self.state["status"] = "complete"
                self._save()
                return self.state
            self._recover_episode(cycle, episode_dir, f"agent_stop:{reason}")
            resume = False
            continue

        self.state["status"] = "time_budget_complete"
        self._save()
        self._log("session_finished", reason="time_budget_complete")
        return self.state
