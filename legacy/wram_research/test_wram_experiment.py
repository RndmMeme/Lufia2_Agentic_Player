import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from wram_discovery.mesen_bridge import (
    SAVE_CURSOR_VALUES,
    MesenFileBridge,
    WRAM_SIZE,
)
from wram_discovery.wram_experiment import ChecklistIndex, analyze_session, compare_sessions


class WramExperimentTests(unittest.TestCase):
    def test_mesen_bridge_ping_read_and_full_dump_protocol(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bridge = MesenFileBridge(root=root, timeout=2.0)
            bridge.start()

            def respond_once(expected_command, response_factory):
                def responder():
                    deadline = time.monotonic() + 2.0
                    request_path = root / "request.txt"
                    while time.monotonic() < deadline and not request_path.exists():
                        time.sleep(0.005)
                    request = request_path.read_text(encoding="utf-8")
                    request_path.unlink()
                    fields = request.split("\t")
                    self.assertEqual(fields[1], expected_command)
                    response = response_factory(fields)
                    (root / "response.txt").write_text(response, encoding="utf-8")

                thread = threading.Thread(target=responder)
                thread.start()
                return thread

            ping_thread = respond_once(
                "PING",
                lambda fields: (
                    f"{fields[0]}\tOK\tPONG\t{WRAM_SIZE}\t"
                    "Lufia II - Rise of the Sinistrals\tABC123\tC:/lufia.sfc"
                ),
            )
            state = bridge.ping()
            ping_thread.join()
            self.assertEqual(state["wram_size"], WRAM_SIZE)
            self.assertIn("Lufia II", state["rom_name"])

            read_thread = respond_once(
                "READ",
                lambda fields: f"{fields[0]}\tOK\tREAD\t9300\t2\t108C",
            )
            self.assertEqual(bridge.read(0x2454, 2), bytes.fromhex("10 8C"))
            read_thread.join()

            def dump_response(fields):
                dump_path = root / f"dump_{fields[0]}.bin"
                dump_path.write_bytes(bytes(WRAM_SIZE))
                return f"{fields[0]}\tOK\tDUMP\t{WRAM_SIZE}\t{dump_path}"

            dump_thread = respond_once("DUMP", dump_response)
            self.assertEqual(len(bridge.dump()), WRAM_SIZE)
            dump_thread.join()

            def probe_response(fields):
                screenshot_path = root / f"probe_{fields[0]}.png"
                screenshot = b"\x89PNG\r\n\x1a\nsynthetic"
                screenshot_path.write_bytes(screenshot)
                return (
                    f"{fields[0]}\tOK\tPROBE\t264\t2\t8834\t"
                    f"{len(screenshot)}\t{screenshot_path}"
                )

            probe_thread = respond_once("PROBE", probe_response)
            value, screenshot = bridge.probe(0x108, 2)
            probe_thread.join()
            self.assertEqual(value, bytes.fromhex("88 34"))
            self.assertTrue(screenshot.startswith(b"\x89PNG"))

    def test_all_seven_save_selection_values_are_unique(self):
        self.assertEqual(
            set(SAVE_CURSOR_VALUES.values()),
            {
                "START",
                "RETRY",
                "GIFT",
                "SAVE FILE 1",
                "SAVE FILE 2",
                "SAVE FILE 3",
                "SAVE FILE 4",
            },
        )
        self.assertEqual(len(SAVE_CURSOR_VALUES), 7)

    def test_campaign_comparison_keeps_only_common_high_score_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sessions = []
            for number, unique_offset in ((1, 0x20), (2, 0x30)):
                session = root / f"session_{number}"
                session.mkdir()
                report = {
                    "label": f"case {number}",
                    "candidates": [
                        {
                            "offset": 0x10,
                            "score": 100.0,
                            "checklist_label": "Textbox aktiv",
                            "transitions": "00->01 x3",
                        },
                        {
                            "offset": unique_offset,
                            "score": 100.0,
                            "checklist_label": "",
                            "transitions": "00->02 x3",
                        },
                    ],
                }
                (session / "candidates.json").write_text(
                    json.dumps(report),
                    encoding="utf-8",
                )
                sessions.append(session)

            output = compare_sessions(sessions, output=root / "comparison.md")
            comparison = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))

            self.assertEqual(comparison["candidate_count"], 1)
            self.assertEqual(comparison["candidates"][0]["offset"], 0x10)

    def test_checklist_maps_legacy_snes9x_addresses_without_label_leak(self):
        checklist_text = """\
19. SAVE, DATEIAUSWAHL UND SPIELMODI
===================================

[x] vier Save-Slot-Strukturen
Cursor @ 0xA32454 - 0xA32455

[x] aktuell markierter Save-Slot
Cursor @ 0xA32454 - 0xA32455

54. UMGERECHNETE ABSOLUTE x64-WRAM-ADRESSEN
===========================================
[MAP] 0xA33534 -> WRAM+0x03534 -> 7E:3534
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            checklist_path = Path(temp_dir) / "checklist.txt"
            checklist_path.write_text(checklist_text, encoding="utf-8")
            checklist = ChecklistIndex(checklist_path)

            expected_label = "vier Save-Slot-Strukturen | aktuell markierter Save-Slot"
            self.assertEqual(checklist.describe(0x0108), ("x", expected_label))
            self.assertEqual(checklist.describe(0x0109), ("x", expected_label))
            self.assertEqual(checklist.describe(0x3534), ("", ""))

    def test_lifecycle_analysis_prefers_reversible_stable_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = Path(temp_dir)
            manifest = {
                "format_version": 2,
                "experiment_type": "lifecycle",
                "label": "Textbox aktiv",
                "trials": [],
            }
            for number in range(1, 4):
                closed_before = bytearray(256)
                opened = bytearray(256)
                open_stable = bytearray(256)
                closed_after = bytearray(256)

                # Desired lifecycle flag.
                opened[0x10] = open_stable[0x10] = 1

                # Consequential animation/noise: changes, but neither holds nor returns.
                opened[0x20] = 1
                open_stable[0x20] = 2
                closed_after[0x20] = 3

                entry = {"number": number}
                for field, data in (
                    ("closed_before", closed_before),
                    ("open", opened),
                    ("open_stable", open_stable),
                    ("closed_after", closed_after),
                ):
                    filename = f"trial_{number:03d}_{field}.bin"
                    (session / filename).write_bytes(data)
                    entry[field] = filename
                manifest["trials"].append(entry)

            (session / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            rows = analyze_session(session)

            self.assertEqual(rows[0]["offset"], 0x10)
            self.assertEqual(rows[0]["score"], 100.0)
            noisy = next(row for row in rows if row["offset"] == 0x20)
            self.assertEqual(noisy["score"], 0.0)

    def test_downward_session_gets_directional_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = Path(temp_dir)
            manifest = {"label": "laufen runter", "trials": []}
            for number in range(1, 4):
                control = bytearray(256)
                before = bytearray(256)
                after = bytearray(256)
                control[0x70] = before[0x70] = 0x10
                after[0x70] = 0x20

                entry = {"number": number}
                for field, data in (
                    ("control_before", control),
                    ("before", before),
                    ("after", after),
                ):
                    filename = f"trial_{number:03d}_{field}.bin"
                    (session / filename).write_bytes(data)
                    entry[field] = filename
                manifest["trials"].append(entry)

            (session / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            analyze_session(session)
            report = json.loads((session / "candidates.json").read_text(encoding="utf-8"))

            self.assertEqual(report["motion_description"], "Runter: Y steigt")
            self.assertEqual(report["motion_candidates"][0]["offset"], 0x70)
            self.assertEqual(report["motion_candidates"][0]["direction_hits"], 3)

    def test_action_signal_outranks_control_noise_and_numeric_match(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = Path(temp_dir)
            manifest = {"label": "synthetic", "trials": []}

            for number in range(1, 4):
                control = bytearray(256)
                before = bytearray(256)
                after = bytearray(256)

                # Natural/control noise: changes before the action too.
                control[0x20] = number
                before[0x20] = number + 1
                after[0x20] = number + 2

                # Repeatable action signal.
                before[0x40] = 0
                after[0x40] = 1

                # Known numeric transition.
                control[0x60] = before[0x60] = 10
                after[0x60] = 9

                names = {}
                for label, data in (
                    ("control", control),
                    ("before", before),
                    ("after", after),
                ):
                    name = f"trial_{number:03d}_{label}.bin"
                    (session / name).write_bytes(data)
                    names[label] = name
                manifest["trials"].append(
                    {
                        "number": number,
                        "control_before": names["control"],
                        "before": names["before"],
                        "after": names["after"],
                    }
                )

            (session / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            rows = analyze_session(
                session,
                expected_before=10,
                expected_after=9,
                widths=(1,),
            )

            self.assertEqual(rows[0]["offset"], 0x40)
            noise = next(row for row in rows if row["offset"] == 0x20)
            self.assertEqual(noise["score"], 0.0)

            report = json.loads((session / "candidates.json").read_text(encoding="utf-8"))
            self.assertEqual(report["numeric_matches"][0]["offset"], 0x60)
            self.assertEqual(report["numeric_matches"][0]["hits"], 3)


if __name__ == "__main__":
    unittest.main()
