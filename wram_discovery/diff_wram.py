from __future__ import annotations

import argparse
import csv
from pathlib import Path


def offset_to_snes_address(offset: int) -> str:
    """
    Erwartet einen 128-KiB-Dump des vollständigen SNES-WRAM:
    Offset 0x00000–0x0FFFF = 7E:0000–7E:FFFF
    Offset 0x10000–0x1FFFF = 7F:0000–7F:FFFF
    """
    if 0 <= offset < 0x10000:
        return f"7E:{offset:04X}"

    if 0x10000 <= offset < 0x20000:
        return f"7F:{offset - 0x10000:04X}"

    return f"OFFSET:{offset:06X}"


def group_contiguous_offsets(offsets: list[int]) -> list[tuple[int, int]]:
    if not offsets:
        return []

    ranges: list[tuple[int, int]] = []
    start = offsets[0]
    previous = offsets[0]

    for offset in offsets[1:]:
        if offset == previous + 1:
            previous = offset
            continue

        ranges.append((start, previous))
        start = offset
        previous = offset

    ranges.append((start, previous))
    return ranges


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vergleicht zwei binäre SNES-WRAM-Dumps."
    )
    parser.add_argument("before", type=Path, help="Ausgangsdump")
    parser.add_argument("after", type=Path, help="Dump nach der Aktion")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("wram_diff.csv"),
        help="Ausgabedatei für alle geänderten Bytes",
    )
    parser.add_argument(
        "--ranges",
        type=Path,
        default=Path("wram_changed_ranges.txt"),
        help="Ausgabedatei für zusammenhängende Änderungsbereiche",
    )
    args = parser.parse_args()

    before = args.before.read_bytes()
    after = args.after.read_bytes()

    if len(before) != len(after):
        raise ValueError(
            f"Unterschiedliche Dateigrößen: "
            f"{args.before.name}={len(before)} Bytes, "
            f"{args.after.name}={len(after)} Bytes"
        )

    changed = [
        offset
        for offset, (old, new) in enumerate(zip(before, after))
        if old != new
    ]

    with args.csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(
            [
                "Offset",
                "SNES-Adresse",
                "Vorher-Hex",
                "Nachher-Hex",
                "Vorher-Dezimal",
                "Nachher-Dezimal",
                "Delta",
            ]
        )

        for offset in changed:
            old = before[offset]
            new = after[offset]

            writer.writerow(
                [
                    f"0x{offset:05X}",
                    offset_to_snes_address(offset),
                    f"0x{old:02X}",
                    f"0x{new:02X}",
                    old,
                    new,
                    new - old,
                ]
            )

    ranges = group_contiguous_offsets(changed)

    with args.ranges.open("w", encoding="utf-8") as file:
        file.write(f"Dumpgröße: {len(before)} Bytes\n")
        file.write(f"Geänderte Bytes: {len(changed)}\n")
        file.write(f"Zusammenhängende Bereiche: {len(ranges)}\n\n")

        for start, end in ranges:
            length = end - start + 1

            file.write(
                f"{offset_to_snes_address(start)}"
                f" – {offset_to_snes_address(end)}"
                f" | Offset 0x{start:05X}–0x{end:05X}"
                f" | {length} Byte(s)\n"
            )

    percentage = len(changed) / len(before) * 100 if before else 0

    print(f"Dumpgröße:            {len(before):,} Bytes")
    print(f"Geänderte Bytes:      {len(changed):,}")
    print(f"Anteil verändert:     {percentage:.2f} %")
    print(f"Änderungsbereiche:    {len(ranges):,}")
    print(f"Byte-Diff:             {args.csv}")
    print(f"Bereichsübersicht:     {args.ranges}")


if __name__ == "__main__":
    main()