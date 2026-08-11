#!/usr/bin/env python3
"""Inspect or cooperatively stop the workspace-global long learning session."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import PROJECT_ROOT
from agent.session_supervisor import STOP_REQUEST_PATH, SUPERVISOR_LOCK_PATH
from run_agent import CONTROLLER_LOCK_PATH, exclusive_file_lock


def lock_available(path: Path, message: str) -> bool:
    try:
        with exclusive_file_lock(path, message):
            return True
    except RuntimeError:
        return False


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.returncode == 0 and f'"{pid}"' in result.stdout


def session_records() -> list[dict]:
    records = []
    runs = PROJECT_ROOT / "data" / "runs"
    paths = sorted(
        runs.glob("long_*/session_state.json"),
        key=lambda item: item.stat().st_mtime,
    )
    for path in paths:
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pid = int(state.get("active_child_pid") or 0)
        records.append({
            "path": str(path),
            "status": state.get("status"),
            "episode": state.get("episode"),
            "cycles": state.get("cycles"),
            "active_child_pid": pid or None,
            "child_alive": pid_alive(pid),
        })
    return records


def print_status() -> int:
    supervisor_active = not lock_available(SUPERVISOR_LOCK_PATH, "status")
    controller_active = not lock_available(CONTROLLER_LOCK_PATH, "status")
    records = session_records()
    print(json.dumps({
        "supervisor_active": supervisor_active,
        "mesen_controller_active": controller_active,
        "stop_requested": STOP_REQUEST_PATH.exists(),
        "latest_sessions": records[-5:],
    }, indent=2, ensure_ascii=False))
    return 0


def assert_clear() -> int:
    supervisor_clear = lock_available(SUPERVISOR_LOCK_PATH, "preflight")
    controller_clear = lock_available(CONTROLLER_LOCK_PATH, "preflight")
    alive = [
        record for record in session_records()
        if record["active_child_pid"] and record["child_alive"]
    ]
    if supervisor_clear and controller_clear and not alive:
        print("Session preflight clear: no supervisor or Mesen controller owns the workspace.")
        return 0
    print("ERROR: A previous learning/controller process is still active.")
    print(json.dumps({
        "supervisor_active": not supervisor_clear,
        "mesen_controller_active": not controller_clear,
        "live_child_records": alive,
    }, indent=2, ensure_ascii=False))
    print("Request a cooperative stop with: start_long_learning_session.bat --stop")
    return 2


def request_stop() -> int:
    STOP_REQUEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    STOP_REQUEST_PATH.write_text(
        json.dumps({
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "requested_by_pid": os.getpid(),
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Cooperative stop requested: {STOP_REQUEST_PATH}")
    print("The agent will stop after its current model call/action completes.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "stop", "assert-clear"))
    args = parser.parse_args()
    return {
        "status": print_status,
        "stop": request_stop,
        "assert-clear": assert_clear,
    }[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
