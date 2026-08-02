import argparse
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.runtime_config import get_helper_executable_path, get_helper_startup_delay
from emulator.memory_reader import MemoryReader


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
        "Memory reader is not ready. Start this tool first, then restart the helper/emulator, or use --launch-helper."
    )


def fmt_byte(value):
    try:
        ivalue = int(value)
    except Exception:
        ivalue = 0
    return f"0x{ivalue:02X} ({ivalue})"


def main():
    parser = argparse.ArgumentParser(description="Compare dungeon coordinate sources live.")
    parser.add_argument("--poll", type=float, default=0.10, help="Refresh interval in seconds.")
    parser.add_argument("--reader-timeout", type=float, default=10.0)
    parser.add_argument("--launch-helper", action="store_true", help="Launch the C# helper after starting the listener.")
    args = parser.parse_args()

    reader = MemoryReader()
    helper_proc = start_helper_if_needed() if args.launch_helper else None

    try:
        wait_for_reader(reader, timeout_sec=args.reader_timeout)
        while True:
            state = reader.get_game_state()
            sys.stdout.write("\033[H\033[J")
            print("=" * 72)
            print("Dungeon Coordinate Compare")
            print("=" * 72)
            print(f"Map:                  {state.get('map_name', 'Unknown')} ({int(state.get('map_id', 0) or 0):02X})")
            print(f"Dungeon X / Y:        {state.get('dungeon_x', 0)} / {state.get('dungeon_y', 0)}")
            print(
                f"Chunk Border H / V:   {state.get('chunk_border_horizontal', 0)} / "
                f"{state.get('chunk_border_vertical', 0)}"
            )
            print(
                f"Spawn X / Y:          {state.get('dungeon_spawn_x', 0)} / "
                f"{state.get('dungeon_spawn_y', 0)}"
            )
            print(
                f"DungeonBlocking:      {fmt_byte(state.get('dungeon_blocking', 255))} "
                f"[{state.get('dungeon_blocking_label', 'clear')}]"
            )
            print(
                f"Map / Runtime Flags:  {fmt_byte(state.get('map_context_flag', 0))} "
                f"[{state.get('map_context_label', 'unknown')}] | "
                f"explore={fmt_byte(state.get('exploration_mode_flag', 0))} | "
                f"battle={fmt_byte(state.get('battle_mode_flag', 0))} | "
                f"{state.get('runtime_mode_label', 'other')}"
            )
            print(
                f"Direction Mirror X:   {fmt_byte(state.get('dungeon_axis_mirror_x', 0))}"
            )
            print(
                f"Direction Mirror Y:   {fmt_byte(state.get('dungeon_axis_mirror_y', 0))}"
            )
            print(
                f"Direction Chunk Y:    {fmt_byte(state.get('dungeon_axis_chunk_y', 0))}"
            )
            print(
                f"Facing Mirror:        {fmt_byte(state.get('facing_contact_state', 0))} "
                f"[{state.get('facing_contact_label', 'unknown')}]"
            )
            print(
                f"Facing / Blocked:     {state.get('facing_direction')} / "
                f"{state.get('blocked_direction') if state.get('blocked_ahead') else 'clear'}"
            )
            print("=" * 72)
            time.sleep(max(0.02, args.poll))
    except KeyboardInterrupt:
        print("\nStopping dungeon coordinate compare...")
    finally:
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
