import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.runtime_config import get_helper_executable_path, get_helper_startup_delay
from emulator.memory_reader import MemoryReader


def wait_for_reader(reader, timeout_sec=10.0):
    deadline = time.time() + max(1.0, timeout_sec)
    while time.time() < deadline:
        state = reader.get_game_state()
        if state.get("_reader_ready"):
            return state
        time.sleep(0.1)
    raise SystemExit(
        "Memory reader is not ready. Start the probe first, then start or restart the helper/emulator so it connects to this listener."
    )


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


def capture_stage(reader, stage_name):
    input(f"\nStage '{stage_name}': get the game into position, then press Enter here...")
    state = reader.get_game_state()
    dump = request_dump(reader)
    return {
        "stage": stage_name,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "state": {
            "map_id": state.get("map_id"),
            "map_name": state.get("map_name"),
            "x": state.get("x"),
            "y": state.get("y"),
            "dungeon_x": state.get("dungeon_x"),
            "dungeon_y": state.get("dungeon_y"),
            "dungeon_blocking": state.get("dungeon_blocking"),
            "in_battle": state.get("in_battle"),
        },
        "dump": dump,
    }


def diff_candidates(base_dump, wall_dump, away_dump):
    candidates = []
    for addr, (b0, b1, b2) in enumerate(zip(base_dump, wall_dump, away_dump)):
        if b0 == b1 == b2:
            continue
        changed_on_wall = b1 != b0
        reverted_after = b2 == b0
        if not changed_on_wall:
            continue
        score = 0
        if reverted_after:
            score += 10
        score += abs(b1 - b0)
        score -= abs(b2 - b0)
        candidates.append(
            {
                "address": addr,
                "address_hex": f"0x{addr:04X}",
                "baseline": b0,
                "wall": b1,
                "away": b2,
                "reverted": reverted_after,
                "score": score,
            }
        )
    candidates.sort(key=lambda item: (-item["score"], not item["reverted"], item["address"]))
    return candidates


def group_contiguous_ranges(candidates):
    addresses = sorted(item["address"] for item in candidates)
    if not addresses:
        return []
    groups = []
    start = prev = addresses[0]
    for addr in addresses[1:]:
        if addr == prev + 1:
            prev = addr
            continue
        groups.append((start, prev))
        start = prev = addr
    groups.append((start, prev))
    return [
        {
            "start": start,
            "end": end,
            "start_hex": f"0x{start:04X}",
            "end_hex": f"0x{end:04X}",
            "length": end - start + 1,
        }
        for start, end in groups
    ]


def save_outputs(output_dir, captures, candidates, ranges):
    output_dir.mkdir(parents=True, exist_ok=True)
    for capture in captures:
        stage = capture["stage"]
        (output_dir / f"{stage}.bin").write_bytes(capture["dump"])
        meta = dict(capture)
        meta.pop("dump", None)
        (output_dir / f"{stage}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    report = {
        "captures": [
            {k: v for k, v in capture.items() if k != "dump"}
            for capture in captures
        ],
        "candidate_count": len(candidates),
        "top_candidates": candidates[:256],
        "candidate_ranges": ranges,
    }
    (output_dir / "collision_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "Collision Probe Report",
        "",
        f"Candidates: {len(candidates)}",
        "",
        "Top candidates:",
    ]
    for item in candidates[:64]:
        lines.append(
            f"{item['address_hex']}: {item['baseline']:02X} -> {item['wall']:02X} -> {item['away']:02X} "
            f"(reverted={item['reverted']}, score={item['score']})"
        )
    lines.extend(["", "Contiguous candidate ranges:"])
    for rng in ranges[:64]:
        lines.append(f"{rng['start_hex']}..{rng['end_hex']} (len={rng['length']})")
    (output_dir / "collision_report.txt").write_text("\n".join(lines), encoding="utf-8")


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Capture baseline/wall/away WRAM dumps and diff likely collision addresses.")
    parser.add_argument("--output-dir", default="data/debug")
    parser.add_argument("--label", default="collision_probe")
    parser.add_argument("--reader-timeout", type=float, default=10.0)
    parser.add_argument("--launch-helper", action="store_true", help="Launch the C# helper after starting the listener.")
    args = parser.parse_args()

    reader = MemoryReader()
    helper_proc = start_helper_if_needed() if args.launch_helper else None
    wait_for_reader(reader, timeout_sec=args.reader_timeout)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = PROJECT_ROOT / args.output_dir / f"{args.label}_{stamp}"

    print("=" * 72)
    print("Collision Probe")
    print("=" * 72)
    print("Plan:")
    print("1. Stand still one tile away from the wall.")
    print("2. Push into the wall so the move fails.")
    print("3. Step away to a normal free tile.")
    print("=" * 72)

    try:
        captures = [
            capture_stage(reader, "baseline"),
            capture_stage(reader, "wall_push"),
            capture_stage(reader, "away"),
        ]

        candidates = diff_candidates(
            captures[0]["dump"],
            captures[1]["dump"],
            captures[2]["dump"],
        )
        ranges = group_contiguous_ranges(candidates[:512])
        save_outputs(output_dir, captures, candidates, ranges)

        print(f"\nSaved probe outputs to: {output_dir}")
        print(f"Top candidate count: {len(candidates)}")
        if candidates:
            print("Top 10 addresses:")
            for item in candidates[:10]:
                print(
                    f"  {item['address_hex']}: {item['baseline']:02X} -> "
                    f"{item['wall']:02X} -> {item['away']:02X} "
                    f"(reverted={item['reverted']}, score={item['score']})"
                )
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
