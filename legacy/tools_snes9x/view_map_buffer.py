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

DEFAULT_START = 0x6421
DEFAULT_END = 0x6FAB
DEFAULT_STRIDE = 0x3A

MAP_WRAP_PRESETS = {
    0x05: 23,  # Secret Skills Cave
}

SEMANTIC_SYMBOLS = {
    0x00: ".",
    0x01: "@",
    0x02: "O",
    0x03: "o",
    0x06: "L",
    0x07: "l",
    0x08: "X",
    0x09: "x",
    0x10: "[",
    0x11: "{",
    0x20: ":",
    0x21: "*",
    0x30: "]",
    0x31: "}",
    0xFF: " ",
}

OBJECT_FAMILIES = {
    0x02: "hole",
    0x03: "hole_variant",
    0x06: "lever",
    0x07: "lever_active",
    0x08: "obstacle",
    0x09: "obstacle_active",
    0x31: "occupied_structural_b",
}


HEX_FAMILIES = {
    0x00: "plain_floor_family",
    0x01: "plain_floor_occupied",
    0x02: "hole_or_gap_family",
    0x03: "hole_or_gap_variant",
    0x06: "lever_family",
    0x07: "lever_family_active",
    0x08: "obstacle_family",
    0x09: "obstacle_family_active",
    0x10: "structural_family_a",
    0x11: "structural_family_a_active",
    0x20: "alternate_floor_family",
    0x21: "alternate_floor_family_active",
    0x30: "structural_family_b",
    0x31: "structural_family_b_active",
    0xFF: "unused_or_blank",
}


def start_helper_if_needed():
    helper_path = get_helper_executable_path(PROJECT_ROOT)
    if not helper_path.exists():
        raise SystemExit(f"Helper not found: {helper_path}")
    process = subprocess.Popen([str(helper_path)], creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(max(1, int(get_helper_startup_delay())))
    return process


def wait_for_reader(reader, timeout_sec=10.0):
    deadline = time.time() + max(1.0, timeout_sec)
    while time.time() < deadline:
        state = reader.get_game_state()
        if state.get("_reader_ready"):
            return state
        time.sleep(0.1)
    raise SystemExit(
        "Memory reader is not ready. Start this tool first, then restart the helper/emulator, or use --launch-helper."
    )


def request_dump(reader, timeout_sec=1.5):
    reader.get_latest_dump()
    reader.send_command("DUMP")
    deadline = time.time() + max(0.5, timeout_sec)
    while time.time() < deadline:
        dump_hex = reader.get_latest_dump()
        if dump_hex:
            return bytes.fromhex(dump_hex)
        time.sleep(0.05)
    raise RuntimeError("Timed out waiting for WRAM dump.")


def build_rows(region, stride):
    return [list(region[start:start + stride]) for start in range(0, len(region), stride)]


def rotate_row(row, wrap_col):
    if not row:
        return row
    if wrap_col <= 0:
        return row
    wrap_col = wrap_col % len(row)
    if wrap_col == 0:
        return row
    return row[wrap_col:] + row[:wrap_col]


def crop_rows(rows, row_offset, col_offset, max_rows, max_cols, wrap_col):
    cropped = rows[row_offset:]
    if max_rows is not None:
        cropped = cropped[:max_rows]
    result = []
    for row in cropped:
        row = rotate_row(row, wrap_col)
        part = row[col_offset:]
        if max_cols is not None:
            part = part[:max_cols]
        result.append(part)
    return result


def render_symbol(value):
    return SEMANTIC_SYMBOLS.get(value, "?")


def family_label(value):
    if value in HEX_FAMILIES:
        return HEX_FAMILIES[value]
    base = value & 0xFE
    if base in HEX_FAMILIES and (value & 1):
        return f"{HEX_FAMILIES[base]}_occupied_like"
    return f"unknown_0x{value:02X}"


def summarize_values(region):
    counts = {}
    for b in region:
        counts[b] = counts.get(b, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def render_row(row, mode):
    if mode == "hex":
        return " ".join(f"{b:02X}" for b in row)
    if mode == "hybrid":
        return " ".join(f"{render_symbol(b)}{b:02X}" for b in row)
    return "".join(render_symbol(b) for b in row)


def build_ruler(width, mode):
    if width <= 0:
        return []
    if mode == "hybrid":
        cell = 3
        top = "".join(str((i // 10) % 10).rjust(cell) for i in range(width))
        bottom = "".join(str(i % 10).rjust(cell) for i in range(width))
        return [top, bottom]
    if mode == "hex":
        cell = 3
        top = "".join(str((i // 10) % 10).rjust(cell) for i in range(width))
        bottom = "".join(str(i % 10).rjust(cell) for i in range(width))
        return [top, bottom]
    top = "".join(str((i // 10) % 10) for i in range(width))
    bottom = "".join(str(i % 10) for i in range(width))
    return [top, bottom]


def trim_active_rows(rows, empty_values=None, min_nonempty=2, padding=1):
    if empty_values is None:
        empty_values = {0x00, 0x20, 0xFF}
    active_indexes = []
    for idx, row in enumerate(rows):
        nonempty = sum(1 for b in row if b not in empty_values)
        if nonempty >= min_nonempty:
            active_indexes.append(idx)
    if not active_indexes:
        return rows, 0
    start = max(0, min(active_indexes) - max(0, padding))
    end = min(len(rows), max(active_indexes) + max(0, padding) + 1)
    return rows[start:end], start


def summarize_objects(rows, row_offset, col_offset, limit=12):
    found = []
    for r_idx, row in enumerate(rows):
        for c_idx, value in enumerate(row):
            if value in OBJECT_FAMILIES:
                found.append({
                    "kind": OBJECT_FAMILIES[value],
                    "value": value,
                    "row": row_offset + r_idx,
                    "col": col_offset + c_idx,
                })
    counts = {}
    for item in found:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    ordered_counts = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return found[:max(0, limit)], ordered_counts


def print_buffer(state, dump, start, end, stride, mode, row_offset, col_offset, max_rows, max_cols, wrap_col, wrap_source, trim_active, trim_padding, summary_limit):
    region = dump[start:end + 1]
    rows = build_rows(region, stride)
    visible_rows = crop_rows(rows, row_offset, col_offset, max_rows, max_cols, wrap_col)
    trimmed_from = 0
    if trim_active:
        visible_rows, trimmed_from = trim_active_rows(visible_rows, padding=trim_padding)

    sys.stdout.write("[H[J")
    print("=" * 100)
    print("Live Map Buffer Viewer")
    print("=" * 100)
    print(f"Map:             {state.get('map_name', 'Unknown')} ({int(state.get('map_id', 0) or 0):02X})")
    print(f"Runtime Mode:    {state.get('runtime_mode_label', 'other')}")
    print(
        f"Context Flags:   map={int(state.get('map_context_flag', 0) or 0):02X} "
        f"explore={int(state.get('exploration_mode_flag', 0) or 0):02X} "
        f"battle={int(state.get('battle_mode_flag', 0) or 0):02X}"
    )
    print(f"Dungeon Pos:     {state.get('dungeon_x', 0)} / {state.get('dungeon_y', 0)}")
    print(f"Blocking:        {int(state.get('dungeon_blocking', 255) or 255):02X} [{state.get('dungeon_blocking_label', 'clear')}]")
    print(f"Region:          0x{start:04X}..0x{end:04X} ({len(region)} bytes)")
    print(f"Row stride:      0x{stride:02X} ({stride})")
    print(f"View window:     row_offset={row_offset} col_offset={col_offset} wrap_col={wrap_col} ({wrap_source}) rows={max_rows or 'all'} cols={max_cols or 'all'}")
    if trim_active:
        print(f"Trim active:     on (padding={trim_padding}, trimmed_from={trimmed_from})")
    print(f"Render mode:     {mode}")
    print("-" * 100)

    visible_width = len(visible_rows[0]) if visible_rows else 0
    for ruler_line in build_ruler(visible_width, mode):
        print("        " + ruler_line)

    for row_idx, row in enumerate(visible_rows):
        absolute_row = row_offset + row_idx
        addr = start + (absolute_row * stride) + col_offset
        rendered = render_row(row, mode)
        print(f"0x{addr:04X}  {rendered}")

    print("-" * 100)
    print("Legend:")
    print("  . = 00 family  @ = 01 occupied  : = 20 family  * = 21 occupied")
    print("  [ = 10 family  { = 11 occupied  ] = 30 family  } = 31 occupied")
    print("  O/o = 02/03 hole-family  L/l = 06/07 lever-family  X/x = 08/09 obstacle-family")
    print("  hybrid mode prints symbol+hex per tile, e.g. :20 or [10")
    object_points, object_counts = summarize_objects(visible_rows, row_offset + trimmed_from, col_offset, limit=summary_limit)
    print("Visible object summary:")
    if object_counts:
        summary = ", ".join(f"{kind}={count}" for kind, count in object_counts)
        print(f"  Counts: {summary}")
        if object_points:
            sample = ", ".join(f"{item['kind']}@r{item['row']}c{item['col']}(0x{item['value']:02X})" for item in object_points)
            print(f"  Sample: {sample}")
    else:
        print("  None detected in visible window")
    print("Top byte counts:")
    for value, count in summarize_values(region)[:16]:
        print(f"  0x{value:02X}: {count:4d}  {family_label(value)}")
    print("=" * 100)


def main():
    parser = argparse.ArgumentParser(description="Read and render the live dungeon map buffer from WRAM.")
    parser.add_argument("--start", type=lambda s: int(s, 0), default=DEFAULT_START)
    parser.add_argument("--end", type=lambda s: int(s, 0), default=DEFAULT_END)
    parser.add_argument("--stride", type=lambda s: int(s, 0), default=DEFAULT_STRIDE)
    parser.add_argument("--poll", type=float, default=0.5, help="Refresh interval in seconds in watch mode.")
    parser.add_argument("--watch", action="store_true", help="Continuously refresh the buffer view.")
    parser.add_argument("--mode", choices=["symbol", "hybrid", "hex"], default="symbol", help="Display mode.")
    parser.add_argument("--hex", action="store_true", help="Alias for --mode hex.")
    parser.add_argument("--row-offset", type=int, default=0, help="Rows to skip from the top of the selected region.")
    parser.add_argument("--col-offset", type=int, default=0, help="Columns to skip from the left of each row after wrapping.")
    parser.add_argument("--wrap-col", type=int, default=None, help="Rotate each row left by this many columns before display. If omitted, known map presets may apply.")
    parser.add_argument("--rows", type=int, default=None, help="Maximum number of rows to display.")
    parser.add_argument("--cols", type=int, default=None, help="Maximum number of columns to display.")
    parser.add_argument("--trim-active", action="store_true", help="Trim mostly empty rows from the visible window.")
    parser.add_argument("--trim-padding", type=int, default=1, help="Extra rows to keep above and below the active band when trimming.")
    parser.add_argument("--summary-limit", type=int, default=12, help="How many visible object positions to sample in the summary.")
    parser.add_argument("--launch-helper", action="store_true", help="Launch the C# helper after starting the listener.")
    parser.add_argument("--reader-timeout", type=float, default=10.0)
    args = parser.parse_args()

    if args.end < args.start:
        raise SystemExit("--end must be >= --start")
    if args.row_offset < 0 or args.col_offset < 0:
        raise SystemExit("Offsets must be >= 0")
    if args.wrap_col is not None and args.wrap_col < 0:
        raise SystemExit("wrap_col must be >= 0")
    if args.rows is not None and args.rows <= 0:
        raise SystemExit("--rows must be > 0")
    if args.cols is not None and args.cols <= 0:
        raise SystemExit("--cols must be > 0")
    if args.trim_padding < 0:
        raise SystemExit("--trim-padding must be >= 0")
    if args.summary_limit < 0:
        raise SystemExit("--summary-limit must be >= 0")

    mode = "hex" if args.hex else args.mode

    reader = MemoryReader()
    helper_proc = start_helper_if_needed() if args.launch_helper else None

    try:
        wait_for_reader(reader, timeout_sec=args.reader_timeout)
        while True:
            state = reader.get_game_state()
            dump = request_dump(reader)
            map_id = int(state.get("map_id", 0) or 0)
            effective_wrap = args.wrap_col if args.wrap_col is not None else MAP_WRAP_PRESETS.get(map_id, 0)
            wrap_source = "manual" if args.wrap_col is not None else ("preset" if map_id in MAP_WRAP_PRESETS else "default")
            print_buffer(
                state,
                dump,
                args.start,
                args.end,
                args.stride,
                mode,
                args.row_offset,
                args.col_offset,
                args.rows,
                args.cols,
                effective_wrap,
                wrap_source,
                args.trim_active,
                args.trim_padding,
                args.summary_limit,
            )
            if not args.watch:
                break
            time.sleep(max(0.05, args.poll))
    except KeyboardInterrupt:
        print("\nStopping live map buffer viewer...")
    finally:
        if helper_proc is not None:
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(helper_proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            except Exception:
                try:
                    helper_proc.terminate()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
