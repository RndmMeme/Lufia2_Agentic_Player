#!/usr/bin/env python3
"""File-based Mesen 2 Lua bridge for coherent SNES WRAM snapshots."""

from __future__ import annotations

import argparse
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Optional


WRAM_SIZE = 0x20000
LEGACY_SNES9X_PREFIX = 0x2314
SAVE_CURSOR_OFFSET = 0x0108
START_TEXT_OFFSET = 0x30C8
START_TEXT = bytes.fromhex("53 20 54 20 41 20 52 20 54 20")
MODULE_ROOT = Path(__file__).resolve().parent
BRIDGE_ROOT = MODULE_ROOT / "mesen_bridge" / "shared"
LUA_SCRIPT = MODULE_ROOT / "mesen_bridge" / "mesen_wram_bridge.lua"
REQUEST_PATH = BRIDGE_ROOT / "request.txt"
RESPONSE_PATH = BRIDGE_ROOT / "response.txt"

SAVE_CURSOR_VALUES = {
    bytes.fromhex("10 14"): "START",
    bytes.fromhex("50 14"): "RETRY",
    bytes.fromhex("90 14"): "GIFT",
    bytes.fromhex("10 34"): "SAVE FILE 1",
    bytes.fromhex("88 34"): "SAVE FILE 2",
    bytes.fromhex("10 8C"): "SAVE FILE 3",
    bytes.fromhex("88 8C"): "SAVE FILE 4",
}
SNES_BUTTONS = {
    "up",
    "down",
    "left",
    "right",
    "a",
    "b",
    "x",
    "y",
    "l",
    "r",
    "start",
    "select",
}


class MesenBridgeError(RuntimeError):
    pass


class MesenFileBridge:
    """Bridge-compatible backend implemented by a Lua script inside Mesen."""

    def __init__(self, root: Path = BRIDGE_ROOT, timeout: float = 10.0):
        self.root = root.resolve()
        self.request_path = self.root / "request.txt"
        self.response_path = self.root / "response.txt"
        self.timeout = timeout
        self.latest_state: dict = {"backend": "mesen"}
        self._lock = threading.Lock()

    def start(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def ensure_helper(self, full_scan: bool = False) -> None:
        del full_scan

    def _request(self, command: str, *arguments: object, timeout: Optional[float] = None) -> list[str]:
        request_id = uuid.uuid4().hex
        payload = "\t".join([request_id, command, *(str(value) for value in arguments)])
        wait_seconds = self.timeout if timeout is None else timeout

        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            self._retry_file_action(lambda: self.response_path.unlink(missing_ok=True))
            temporary = self.request_path.with_suffix(".tmp")
            temporary.write_text(payload, encoding="utf-8")
            self._retry_file_action(lambda: os.replace(temporary, self.request_path))

            deadline = time.monotonic() + wait_seconds
            while time.monotonic() < deadline:
                if self.response_path.exists():
                    try:
                        response = self.response_path.read_text(
                            encoding="utf-8",
                            errors="replace",
                        ).strip()
                    except OSError:
                        time.sleep(0.02)
                        continue
                    fields = response.split("\t")
                    if fields and fields[0] == request_id:
                        self._retry_file_action(
                            lambda: self.response_path.unlink(missing_ok=True)
                        )
                        if len(fields) < 2 or fields[1] != "OK":
                            message = fields[2] if len(fields) > 2 else "unknown Mesen bridge error"
                            raise MesenBridgeError(message)
                        return fields[2:]
                time.sleep(0.025)

            self._retry_file_action(lambda: self.request_path.unlink(missing_ok=True))
            raise TimeoutError(
                "Keine Antwort von Mesen. Lade das Lua-Script "
                f"'{LUA_SCRIPT}' im Script Window, aktiviere 'Allow access to I/O "
                "and OS functions' und starte es mit F5."
            )

    @staticmethod
    def _retry_file_action(action, timeout: float = 2.0) -> None:
        """Retry short-lived Windows sharing violations from Mesen's Lua I/O."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                action()
                return
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)

    def ping(self) -> dict:
        fields = self._request("PING", timeout=2.0)
        if len(fields) < 4 or fields[0] != "PONG":
            raise MesenBridgeError(f"Ungültige PING-Antwort: {fields!r}")
        state = {
            "backend": "mesen",
            "wram_size": int(fields[1]),
            "rom_name": fields[2],
            "rom_sha1": fields[3],
            "rom_path": fields[4] if len(fields) > 4 else "",
            "protocol_version": int(fields[5]) if len(fields) > 5 else 1,
        }
        self.latest_state = state
        return state

    def wait_attached(self, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                state = self.ping()
                return state["wram_size"] == WRAM_SIZE
            except (OSError, TimeoutError, MesenBridgeError, ValueError):
                time.sleep(0.2)
        return False

    def dump(self) -> bytes:
        fields = self._request("DUMP", timeout=max(self.timeout, 15.0))
        if len(fields) < 3 or fields[0] != "DUMP":
            raise MesenBridgeError(f"Ungültige DUMP-Antwort: {fields!r}")
        expected_size = int(fields[1])
        dump_path = Path(fields[2])
        deadline = time.monotonic() + 3.0
        try:
            while True:
                try:
                    data = dump_path.read_bytes()
                except (FileNotFoundError, PermissionError):
                    data = b""
                if len(data) == expected_size:
                    break
                if time.monotonic() >= deadline:
                    raise MesenBridgeError(
                        f"Mesen-Dump blieb unvollständig: {len(data)} "
                        f"von {expected_size} Bytes."
                    )
                time.sleep(0.02)
        finally:
            self._retry_file_action(lambda: dump_path.unlink(missing_ok=True))
        if expected_size != WRAM_SIZE or len(data) != WRAM_SIZE:
            raise MesenBridgeError(
                f"Mesen lieferte {len(data)} Bytes (gemeldet: {expected_size}) "
                f"statt {WRAM_SIZE}."
            )
        return data

    def read(self, offset: int, length: int = 1) -> bytes:
        if offset < 0 or length < 1 or offset + length > WRAM_SIZE:
            raise ValueError("READ liegt außerhalb des 128-KiB-SNES-WRAM.")
        fields = self._request("READ", offset, length)
        if len(fields) < 4 or fields[0] != "READ":
            raise MesenBridgeError(f"Ungültige READ-Antwort: {fields!r}")
        data = bytes.fromhex(fields[3])
        if len(data) != length:
            raise MesenBridgeError(f"READ lieferte {len(data)} statt {length} Bytes.")
        return data

    def screenshot(self) -> bytes:
        fields = self._request("SCREENSHOT")
        if len(fields) < 3 or fields[0] != "SCREENSHOT":
            raise MesenBridgeError(f"Ungültige SCREENSHOT-Antwort: {fields!r}")
        expected_size = int(fields[1])
        screenshot_path = Path(fields[2])
        try:
            data = screenshot_path.read_bytes()
        finally:
            screenshot_path.unlink(missing_ok=True)
        if len(data) != expected_size or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise MesenBridgeError("Mesen lieferte keinen gültigen PNG-Screenshot.")
        return data

    def probe(self, offset: int, length: int = 1) -> tuple[bytes, bytes]:
        if offset < 0 or length < 1 or offset + length > WRAM_SIZE:
            raise ValueError("PROBE liegt außerhalb des 128-KiB-SNES-WRAM.")
        fields = self._request("PROBE", offset, length)
        if len(fields) < 6 or fields[0] != "PROBE":
            raise MesenBridgeError(f"Ungültige PROBE-Antwort: {fields!r}")
        data = bytes.fromhex(fields[3])
        expected_png_size = int(fields[4])
        screenshot_path = Path(fields[5])
        try:
            screenshot = screenshot_path.read_bytes()
        finally:
            screenshot_path.unlink(missing_ok=True)
        if len(data) != length:
            raise MesenBridgeError(f"PROBE lieferte {len(data)} statt {length} Bytes.")
        if (
            len(screenshot) != expected_png_size
            or not screenshot.startswith(b"\x89PNG\r\n\x1a\n")
        ):
            raise MesenBridgeError("PROBE lieferte keinen gültigen PNG-Screenshot.")
        return data, screenshot

    def pulse(self, button: str, frames: int = 2, settle_seconds: float = 0.25) -> None:
        normalized = button.casefold()
        if normalized not in SNES_BUTTONS:
            raise ValueError(f"Unbekannter SNES-Button: {button}")
        if not 1 <= frames <= 30:
            raise ValueError("frames muss zwischen 1 und 30 liegen.")
        fields = self._request("PULSE", normalized, frames)
        if len(fields) < 3 or fields[0] != "PULSE":
            raise MesenBridgeError(f"Ungültige PULSE-Antwort: {fields!r}")
        time.sleep(max(settle_seconds, (frames + 6) / 60.0))

    def chord(
        self,
        held_button: str,
        pressed_button: str,
        lead_frames: int = 2,
        press_frames: int = 2,
        settle_seconds: float = 0.25,
    ) -> None:
        """Hold one button, add a second, then release both on frame boundaries."""
        held = held_button.casefold()
        pressed = pressed_button.casefold()
        if held not in SNES_BUTTONS or pressed not in SNES_BUTTONS or held == pressed:
            raise ValueError("CHORD requires two different known SNES buttons")
        if not 1 <= lead_frames <= 30 or not 1 <= press_frames <= 30:
            raise ValueError("CHORD frame counts must be between 1 and 30")
        fields = self._request("CHORD", held, pressed, lead_frames, press_frames)
        if len(fields) < 5 or fields[0] != "CHORD":
            raise MesenBridgeError(f"Ungültige CHORD-Antwort: {fields!r}")
        total_frames = lead_frames + press_frames + 4
        time.sleep(max(settle_seconds, total_frames / 60.0))

    def input_state(self) -> str:
        fields = self._request("GETINPUT")
        if len(fields) < 2 or fields[0] != "GETINPUT":
            raise MesenBridgeError(f"Ungültige GETINPUT-Antwort: {fields!r}")
        return fields[1]

    def hold_until(
        self,
        button: str,
        offset: int,
        expected_value: int,
        max_frames: int = 3600,
    ) -> None:
        """Continuously hold a button until one WRAM byte reaches a value."""
        normalized = button.casefold()
        if normalized not in SNES_BUTTONS:
            raise ValueError(f"Unbekannter SNES-Button: {button}")
        if not 0 <= offset < WRAM_SIZE or not 0 <= expected_value <= 0xFF:
            raise ValueError("Invalid HOLD_UNTIL WRAM condition")
        if not 1 <= max_frames <= 3600:
            raise ValueError("max_frames must be between 1 and 3600")
        if self.read(offset, 1)[0] == expected_value:
            return
        fields = self._request(
            "HOLD_UNTIL", normalized, offset, expected_value, max_frames
        )
        if len(fields) < 5 or fields[0] != "HOLD_UNTIL":
            raise MesenBridgeError(f"UngÃ¼ltige HOLD_UNTIL-Antwort: {fields!r}")
        deadline = time.monotonic() + max_frames / 60.0 + 2.0
        while time.monotonic() < deadline:
            if self.read(offset, 1)[0] == expected_value:
                time.sleep(0.1)
                return
            time.sleep(0.05)
        raise TimeoutError(
            f"Held {normalized} for at most {max_frames} frames, but "
            f"WRAM 0x{offset:05X} did not become 0x{expected_value:02X}"
        )

    def close(self) -> None:
        pass


def doctor(bridge: MesenFileBridge) -> int:
    bridge.start()
    state = bridge.ping()
    dump = bridge.dump()
    print("MESEN-LIVE-OK")
    print(f"  ROM: {state['rom_name']}")
    print(f"  SHA-1: {state['rom_sha1']}")
    print(f"  WRAM: {len(dump)} Bytes (7E:0000-7F:FFFF)")
    print(f"  Bridge protocol: {state['protocol_version']}")
    return 0


def verify_save_cursor(bridge: MesenFileBridge) -> int:
    state = bridge.ping()
    value = bridge.read(SAVE_CURSOR_OFFSET, 2)
    start_text = bridge.read(START_TEXT_OFFSET, len(START_TEXT))
    meaning = SAVE_CURSOR_VALUES.get(value)
    print(f"ROM: {state['rom_name']}")
    print(
        f"Save-Cursor @ 7E:{SAVE_CURSOR_OFFSET:04X}-"
        f"{SAVE_CURSOR_OFFSET + 1:04X} = {value.hex(' ').upper()}"
    )
    if meaning:
        print(f"  Zugeordnet: {meaning}")
    else:
        print("  Momentaner Wert ist noch keinem Save-Eintrag semantisch zugeordnet.")
    print(
        f"START-Text @ 7E:{START_TEXT_OFFSET:04X} = "
        f"{start_text.hex(' ').upper()}"
    )
    if start_text == START_TEXT:
        print("PLAUSIBEL: Echte Mesen-WRAM-Adresse und bekannter Textinhalt stimmen.")
        return 0
    print("NICHT PLAUSIBEL: Der bekannte START-Text wurde nicht gefunden.")
    return 2


def parse_int(value: str) -> int:
    return int(value, 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Mesen-Lua-Bridge für SNES-WRAM.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor")
    subparsers.add_parser("verify-save")
    read_parser = subparsers.add_parser("read")
    read_parser.add_argument("offset", type=parse_int)
    read_parser.add_argument("length", type=parse_int, nargs="?", default=1)
    dump_parser = subparsers.add_parser("dump")
    dump_parser.add_argument("output", type=Path)
    screenshot_parser = subparsers.add_parser("screenshot")
    screenshot_parser.add_argument("output", type=Path)
    press_parser = subparsers.add_parser("press")
    press_parser.add_argument("button", choices=sorted(SNES_BUTTONS))
    press_parser.add_argument("--frames", type=int, default=2)
    chord_parser = subparsers.add_parser("chord")
    chord_parser.add_argument("held_button", choices=sorted(SNES_BUTTONS))
    chord_parser.add_argument("pressed_button", choices=sorted(SNES_BUTTONS))
    chord_parser.add_argument("--lead-frames", type=int, default=2)
    chord_parser.add_argument("--press-frames", type=int, default=2)
    subparsers.add_parser("input-state")
    hold_parser = subparsers.add_parser("hold-until")
    hold_parser.add_argument("button", choices=sorted(SNES_BUTTONS))
    hold_parser.add_argument("offset", type=parse_int)
    hold_parser.add_argument("expected_value", type=parse_int)
    hold_parser.add_argument("--max-frames", type=int, default=3600)
    probe_parser = subparsers.add_parser("probe")
    probe_parser.add_argument("offset", type=parse_int)
    probe_parser.add_argument("length", type=parse_int)
    probe_parser.add_argument("screenshot", type=Path)
    args = parser.parse_args()

    bridge = MesenFileBridge()
    try:
        if args.command == "doctor":
            return doctor(bridge)
        if args.command == "verify-save":
            return verify_save_cursor(bridge)
        if args.command == "read":
            data = bridge.read(args.offset, args.length)
            print(data.hex(" ").upper())
            return 0
        if args.command == "dump":
            data = bridge.dump()
            args.output.write_bytes(data)
            print(f"{len(data)} Bytes: {args.output.resolve()}")
            return 0
        if args.command == "screenshot":
            data = bridge.screenshot()
            args.output.write_bytes(data)
            print(f"{len(data)} Bytes: {args.output.resolve()}")
            return 0
        if args.command == "press":
            bridge.pulse(args.button, args.frames)
            print(f"SNES-Button gesendet: {args.button} ({args.frames} Frames)")
            return 0
        if args.command == "chord":
            bridge.chord(
                args.held_button,
                args.pressed_button,
                lead_frames=args.lead_frames,
                press_frames=args.press_frames,
            )
            print(
                "SNES-Kombination gesendet: "
                f"{args.held_button}+{args.pressed_button} "
                f"({args.lead_frames}+{args.press_frames} Frames)"
            )
            return 0
        if args.command == "input-state":
            print(bridge.input_state())
            return 0
        if args.command == "hold-until":
            bridge.hold_until(
                args.button,
                args.offset,
                args.expected_value,
                max_frames=args.max_frames,
            )
            print(
                f"{args.button} gehalten bis 0x{args.offset:05X}="
                f"0x{args.expected_value:02X}"
            )
            return 0
        if args.command == "probe":
            data, screenshot = bridge.probe(args.offset, args.length)
            args.screenshot.write_bytes(screenshot)
            print(data.hex(" ").upper())
            print(f"Screenshot: {args.screenshot.resolve()}")
            return 0
        raise AssertionError(args.command)
    except (MesenBridgeError, TimeoutError, OSError, ValueError) as exc:
        print(f"FEHLER: {exc}")
        return 1
    finally:
        bridge.close()


if __name__ == "__main__":
    raise SystemExit(main())
