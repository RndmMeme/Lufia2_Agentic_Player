import argparse
import os
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
import json


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.runtime_config import get_helper_executable_path, get_helper_startup_delay
from emulator.memory_reader import MemoryReader


WATCH_FIELDS = [
    "map_id",
    "map_name",
    "x",
    "y",
    "dungeon_x",
    "dungeon_y",
    "dungeon_blocking",
    "dungeon_blocking_label",
    "map_context_flag",
    "map_context_label",
    "exploration_mode_flag",
    "battle_mode_flag",
    "runtime_mode_label",
    "facing_contact_state",
    "facing_contact_label",
    "facing_direction",
    "blocked_ahead",
    "blocked_direction",
    "chunk_border_vertical",
    "chunk_border_horizontal",
    "dungeon_spawn_x",
    "dungeon_spawn_y",
    "town_x",
    "town_y",
    "town_v_chunk",
    "town_h_chunk",
    "in_battle",
    "_reader_packet_count",
]


def start_helper_if_needed():
    helper_path = get_helper_executable_path(PROJECT_ROOT)
    if not helper_path.exists():
        raise SystemExit(f"Helper not found: {helper_path}")
    process = subprocess.Popen(
        [str(helper_path)],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    time.sleep(max(1, int(get_helper_startup_delay())))
    return process


def wait_for_reader(reader, timeout_sec=10.0):
    deadline = time.time() + max(1.0, timeout_sec)
    while time.time() < deadline:
        state = reader.get_game_state()
        if state.get("_reader_ready"):
            return
        time.sleep(0.1)
    raise SystemExit(
        "Memory reader is not ready. Start this watcher first, then restart the helper/emulator, or use --launch-helper."
    )


def raw_state_snapshot(reader):
    with reader._lock:
        state = dict(reader.latest_state or {})
    merged = reader.get_game_state()
    for key, value in merged.items():
        state.setdefault(key, value)
    return state


def fmt_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def main():
    parser = argparse.ArgumentParser(description="Live-watch dungeon navigation fields from the helper stream.")
    parser.add_argument("--poll", type=float, default=0.10, help="Refresh interval in seconds.")
    parser.add_argument("--history", type=int, default=24, help="Number of recent changes to keep.")
    parser.add_argument("--reader-timeout", type=float, default=10.0)
    parser.add_argument("--launch-helper", action="store_true", help="Launch the C# helper after starting the listener.")
    parser.add_argument(
        "--log-file",
        help="Optional path to write change-only JSONL logs. Defaults to data/debug/live_nav_watch_<timestamp>.jsonl",
    )
    args = parser.parse_args()

    reader = MemoryReader()
    helper_proc = start_helper_if_needed() if args.launch_helper else None
    log_path = None
    log_handle = None

    try:
        wait_for_reader(reader, timeout_sec=args.reader_timeout)
        last_values = {}
        history = deque(maxlen=max(4, args.history))
        if args.log_file:
            log_path = Path(args.log_file)
        else:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            log_path = PROJECT_ROOT / "data" / "debug" / f"live_nav_watch_{stamp}.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("a", encoding="utf-8")

        while True:
            state = raw_state_snapshot(reader)
            changed = []
            for field in WATCH_FIELDS:
                value = state.get(field)
                if last_values.get(field) != value:
                    if field in last_values:
                        changed.append((field, last_values[field], value))
                    last_values[field] = value

            if changed:
                stamp = time.strftime("%H:%M:%S")
                for field, old, new in changed:
                    history.appendleft(f"{stamp} {field}: {fmt_value(old)} -> {fmt_value(new)}")
                log_record = {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "state": {field: state.get(field) for field in WATCH_FIELDS},
                    "changed": [
                        {"field": field, "old": old, "new": new}
                        for field, old, new in changed
                    ],
                }
                log_handle.write(json.dumps(log_record) + "\n")
                log_handle.flush()

            sys.stdout.write("\033[H\033[J")
            print("=" * 72)
            print("Live Navigation Watch")
            print("=" * 72)
            print("Press against a wall or move away. Changed fields are logged below.")
            print(f"Log file: {log_path}")
            print("-" * 72)
            for field in WATCH_FIELDS:
                value = state.get(field)
                marker = "*" if any(entry[0] == field for entry in changed) else " "
                print(f"{marker} {field:22} {fmt_value(value)}")
            print("-" * 72)
            print("Recent changes:")
            for line in history:
                print(line)
            print("=" * 72)
            time.sleep(max(0.02, args.poll))
    except KeyboardInterrupt:
        print("\nStopping live navigation watcher...")
    finally:
        if log_handle is not None:
            try:
                log_handle.close()
            except Exception:
                pass
        if helper_proc is not None:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(helper_proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            except Exception:
                try:
                    helper_proc.terminate()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
