import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from pathlib import Path
from unittest.mock import Mock

from wram_discovery.mesen_bridge import SAVE_CURSOR_VALUES, MesenFileBridge, WRAM_SIZE


class MesenBridgeProtocolTests(unittest.TestCase):
    def test_publish_request_falls_back_to_persistent_windows_mailbox(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bridge = MesenFileBridge(root=root, timeout=2.0)
            bridge.start()
            bridge.request_path.write_text("", encoding="utf-8")

            with patch("wram_discovery.mesen_bridge.os.replace", side_effect=PermissionError):
                bridge._publish_request("request-id\tPING")

            self.assertEqual(
                bridge.request_path.read_text(encoding="utf-8"),
                "request-id\tPING",
            )
            self.assertFalse(bridge.request_path.with_suffix(".tmp").exists())
            self.assertTrue(bridge._persistent_mailbox)

            with patch("wram_discovery.mesen_bridge.os.replace") as replace:
                bridge._publish_request("second-id\tPING")
            replace.assert_not_called()
            self.assertEqual(
                bridge.request_path.read_text(encoding="utf-8"),
                "second-id\tPING",
            )

    def test_lua_acknowledges_before_processing(self):
        lua = (Path(__file__).parent / "mesen_bridge" / "mesen_wram_bridge.lua").read_text(
            encoding="utf-8"
        )
        ack = lua.index("if not acknowledgeRequest() then")
        process = lua.index("pcall(processRequest, request)")
        self.assertLess(ack, process)

    def test_ping_read_dump_and_probe_protocol(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bridge = MesenFileBridge(root=root, timeout=2.0)
            bridge.start()

            def respond_once(expected_command, response_factory):
                def responder():
                    request_path = root / "request.txt"
                    deadline = time.monotonic() + 2.0
                    while time.monotonic() < deadline and not request_path.exists():
                        time.sleep(0.005)
                    fields = request_path.read_text(encoding="utf-8").split("\t")
                    request_path.unlink()
                    self.assertEqual(fields[1], expected_command)
                    (root / "response.txt").write_text(response_factory(fields), encoding="utf-8")

                thread = threading.Thread(target=responder)
                thread.start()
                return thread

            thread = respond_once(
                "PING",
                lambda fields: f"{fields[0]}\tOK\tPONG\t{WRAM_SIZE}\tLufia II\tABC123\tC:/lufia.sfc\t2",
            )
            ping = bridge.ping()
            self.assertEqual(ping["wram_size"], WRAM_SIZE)
            self.assertEqual(ping["protocol_version"], 2)
            thread.join()

            thread = respond_once("READ", lambda fields: f"{fields[0]}\tOK\tREAD\t9300\t2\t108C")
            self.assertEqual(bridge.read(0x2454, 2), bytes.fromhex("10 8C"))
            thread.join()

            def dump_response(fields):
                path = root / f"dump_{fields[0]}.bin"
                path.write_bytes(bytes(WRAM_SIZE))
                return f"{fields[0]}\tOK\tDUMP\t{WRAM_SIZE}\t{path}"

            thread = respond_once("DUMP", dump_response)
            self.assertEqual(len(bridge.dump()), WRAM_SIZE)
            thread.join()

            def probe_response(fields):
                path = root / f"probe_{fields[0]}.png"
                screenshot = b"\x89PNG\r\n\x1a\nsynthetic"
                path.write_bytes(screenshot)
                return f"{fields[0]}\tOK\tPROBE\t264\t2\t8834\t{len(screenshot)}\t{path}"

            thread = respond_once("PROBE", probe_response)
            value, screenshot = bridge.probe(0x108, 2)
            thread.join()
            self.assertEqual(value, bytes.fromhex("88 34"))
            self.assertTrue(screenshot.startswith(b"\x89PNG"))

    def test_save_selection_values_are_unique(self):
        self.assertEqual(len(SAVE_CURSOR_VALUES), 7)
        self.assertEqual(len(set(SAVE_CURSOR_VALUES.values())), 7)

    def test_chord_protocol_keeps_direction_held_while_confirming(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bridge = MesenFileBridge(root=root, timeout=2.0)
            bridge.start()

            def responder():
                request_path = root / "request.txt"
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline and not request_path.exists():
                    time.sleep(0.005)
                fields = request_path.read_text(encoding="utf-8").split("\t")
                request_path.unlink()
                self.assertEqual(fields[1:], ["CHORD", "left", "a", "2", "2"])
                (root / "response.txt").write_text(
                    f"{fields[0]}\tOK\tCHORD\tleft\ta\t2\t2", encoding="utf-8"
                )

            thread = threading.Thread(target=responder)
            thread.start()
            bridge.chord("left", "a", settle_seconds=0)
            thread.join()

        lua = (Path(__file__).parent / "mesen_bridge" / "mesen_wram_bridge.lua").read_text(
            encoding="utf-8"
        )
        self.assertIn('if command == "CHORD" then', lua)
        self.assertIn("input[pendingPulse.leadButton] = true", lua)

    def test_hold_until_uses_wram_terminated_continuous_input(self):
        bridge = MesenFileBridge(timeout=2.0)
        bridge.read = Mock(side_effect=[b"\x01", b"\x00"])
        bridge._request = Mock(
            return_value=["HOLD_UNTIL", "a", "2474", "0", "3600"]
        )
        bridge.hold_until("a", 0x09AA, 0, max_frames=3600)
        bridge._request.assert_called_once_with("HOLD_UNTIL", "a", 0x09AA, 0, 3600)

        lua = (Path(__file__).parent / "mesen_bridge" / "mesen_wram_bridge.lua").read_text(
            encoding="utf-8"
        )
        self.assertIn('if command == "HOLD_UNTIL" then', lua)
        self.assertIn("pendingPulse.stopOffset", lua)


if __name__ == "__main__":
    unittest.main()
