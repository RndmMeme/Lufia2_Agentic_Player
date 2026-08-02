#!/usr/bin/env python3
"""
Repeatable, action-correlated WRAM experiments for Lufia II.

The tool talks to the existing C# helper, stores full binary snapshots and
ranks addresses that change during a labelled action but stay quiet during an
equally long control window.

Examples:
    python wram_discovery/wram_experiment.py capture --label textbox_open --trials 5
    python wram_discovery/wram_experiment.py capture --label menu_down --keys down --trials 8
    python wram_discovery/wram_experiment.py analyze wram_discovery/sessions/<session>
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

try:
    from .mesen_bridge import (
        LUA_SCRIPT,
        SAVE_CURSOR_OFFSET,
        SAVE_CURSOR_VALUES,
        MesenFileBridge,
    )
except ImportError:
    from mesen_bridge import (
        LUA_SCRIPT,
        SAVE_CURSOR_OFFSET,
        SAVE_CURSOR_VALUES,
        MesenFileBridge,
    )


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = Path(__file__).resolve().parent / "sessions"
CHECKLIST_GLOB = "lufia2_wram_checklist_merged* v5.txt"
WRAM_SIZE = 0x20000
HOST = "127.0.0.1"
PORT = 64321

SNES_KEY_MAP = {
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "a": "x",
    "b": "z",
    "x": "s",
    "y": "a",
    "l": "q",
    "r": "w",
    "start": "enter",
    "select": "space",
}


def slugify(value: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_")
    return result or "experiment"


def bus_address(offset: int) -> str:
    if 0 <= offset < 0x10000:
        return f"7E:{offset:04X}"
    if 0x10000 <= offset < WRAM_SIZE:
        return f"7F:{offset - 0x10000:04X}"
    return f"WRAM+0x{offset:05X}"


def find_checklist() -> Optional[Path]:
    docs = PROJECT_ROOT / "docs"
    candidates = sorted(docs.glob("*wram*checklist*update_v5.txt"))
    if not candidates:
        candidates = sorted(docs.glob("*wram*checklist*v5.txt"))
    return candidates[-1] if candidates else None


@dataclass(frozen=True)
class ChecklistEntry:
    status: str
    label: str


class ChecklistIndex:
    """Best-effort index of addresses already mentioned by the v5 checklist."""

    ADDRESS_RE = re.compile(
        r"(?:\b(7E|7F):([0-9A-Fa-f]{4})\b|WRAM\+0x([0-9A-Fa-f]{4,5}))",
        re.IGNORECASE,
    )
    LEGACY_HOST_ADDRESS_RE = re.compile(r"\b0x(A[3-5][0-9A-Fa-f]{4})\b", re.IGNORECASE)
    ENTRY_RE = re.compile(r"^\[([ x~!])\]\s*(.+)$")
    SECTION_RE = re.compile(r"^\d+\.\s+\S")
    NON_ENTRY_TAG_RE = re.compile(r"^\[(?:MAP|REF|ROM|PROC)\]", re.IGNORECASE)
    LEGACY_HOST_OVERRIDES = {
        0xA32454: 0x0108,
        0xA32455: 0x0109,
    }

    def __init__(self, path: Optional[Path]):
        self.path = path
        self.entries: dict[int, list[ChecklistEntry]] = defaultdict(list)
        if path and path.exists():
            self._parse(path)

    @staticmethod
    def _short_label(raw: str) -> str:
        for separator in (" — ", " â€” ", " - "):
            if separator in raw:
                raw = raw.split(separator, 1)[0]
        return raw.strip()

    def _parse(self, path: Path) -> None:
        current: Optional[ChecklistEntry] = None
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            match = self.ENTRY_RE.match(stripped)
            if match:
                current = ChecklistEntry(match.group(1), self._short_label(match.group(2)))
            elif (
                self.SECTION_RE.match(stripped)
                or self.NON_ENTRY_TAG_RE.match(stripped)
                or (len(stripped) >= 3 and set(stripped) <= {"=", "-"})
            ):
                # Do not leak the last checkbox label into later summary/map sections.
                current = None
            if not current:
                continue

            offsets = []
            for address in self.ADDRESS_RE.finditer(line):
                if address.group(3):
                    offset = int(address.group(3), 16)
                else:
                    bank = address.group(1).upper()
                    offset = int(address.group(2), 16) + (0x10000 if bank == "7F" else 0)
                offsets.append(offset)

            # Older manually curated entries use absolute x64 Snes9x addresses.
            # Most bulk data aligns against Mesen with a -0x2314 prefix, but
            # Snes9x process structures are not globally linear. Addresses
            # proven live in Mesen therefore override the best-effort fallback.
            for address in self.LEGACY_HOST_ADDRESS_RE.finditer(line):
                host_address = int(address.group(1), 16)
                offset = self.LEGACY_HOST_OVERRIDES.get(
                    host_address,
                    host_address - 0xA32314,
                )
                if 0 <= offset < WRAM_SIZE:
                    offsets.append(offset)

            for offset in offsets:
                if current not in self.entries[offset]:
                    self.entries[offset].append(current)

    def describe(self, offset: int) -> tuple[str, str]:
        entries = self.entries.get(offset, [])
        if not entries:
            return "", ""
        status_order = {"x": 0, "~": 1, "!": 2, " ": 3}
        best_rank = min(status_order.get(entry.status, 9) for entry in entries)
        best_entries = [
            entry for entry in entries if status_order.get(entry.status, 9) == best_rank
        ]
        labels = list(dict.fromkeys(entry.label for entry in best_entries))
        status = best_entries[0].status.strip() or "open"
        return status, " | ".join(labels)


class HelperBridge:
    """Small TCP server implementing the helper's existing line protocol."""

    def __init__(self, host: str = HOST, port: int = PORT):
        self.host = host
        self.port = port
        self._listener: Optional[socket.socket] = None
        self._connection: Optional[socket.socket] = None
        self._running = threading.Event()
        self._connected = threading.Event()
        self._condition = threading.Condition()
        self._dump_generation = 0
        self._latest_dump: Optional[bytes] = None
        self.latest_state: dict = {}
        self.spawned_helper: Optional[subprocess.Popen] = None

    def start(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((self.host, self.port))
        except OSError as exc:
            listener.close()
            raise RuntimeError(
                f"Port {self.port} ist belegt. Beende zuerst main.py/MemoryReader "
                "oder ein anderes Discovery-Tool."
            ) from exc
        listener.listen(2)
        listener.settimeout(0.5)
        self._listener = listener
        self._running.set()
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self) -> None:
        assert self._listener is not None
        while self._running.is_set():
            try:
                connection, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with self._condition:
                old = self._connection
                self._connection = connection
                self._connected.set()
                if old:
                    try:
                        old.close()
                    except OSError:
                        pass
            threading.Thread(target=self._read_loop, args=(connection,), daemon=True).start()

    def _read_loop(self, connection: socket.socket) -> None:
        pending = b""
        try:
            while self._running.is_set():
                chunk = connection.recv(65536)
                if not chunk:
                    break
                pending += chunk
                while b"\n" in pending:
                    raw_line, pending = pending.split(b"\n", 1)
                    if not raw_line.strip():
                        continue
                    try:
                        payload = json.loads(raw_line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("type") == "dump":
                        try:
                            dump = bytes.fromhex(payload.get("data", ""))
                        except ValueError:
                            continue
                        with self._condition:
                            self._latest_dump = dump
                            self._dump_generation += 1
                            self._condition.notify_all()
                    elif payload.get("type") not in {"dump_ready", "info"}:
                        with self._condition:
                            self.latest_state.update(payload)
                            self._condition.notify_all()
        except OSError:
            # Normal when the probe closes the socket after a completed run.
            pass
        finally:
            with self._condition:
                if self._connection is connection:
                    self._connection = None
                    self._connected.clear()

    def wait_connected(self, timeout: float) -> bool:
        return self._connected.wait(timeout)

    def send(self, command: str) -> None:
        with self._condition:
            connection = self._connection
        if not connection:
            raise RuntimeError("C# Helper ist nicht verbunden.")
        connection.sendall((command + "\n").encode("ascii"))

    def dump(self, timeout: float = 8.0) -> bytes:
        with self._condition:
            generation = self._dump_generation
        self.send("DUMP")
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._dump_generation == generation:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Kein WRAM-Dump innerhalb des Zeitlimits empfangen.")
                self._condition.wait(remaining)
            assert self._latest_dump is not None
            return self._latest_dump

    def ensure_helper(self, timeout: float = 20.0, full_scan: bool = False) -> None:
        # An already running helper retries its connection during state updates.
        if self.wait_connected(3.0):
            return
        helper = find_helper_executable()
        if not helper:
            raise FileNotFoundError(
                "Lufia2AutoTracker.Helper.exe fehlt. Zuerst den C# Helper bauen."
            )
        creation_flags = 0x08000000 if os.name == "nt" else 0
        helper_args = [str(helper), "--data-dir", str(PROJECT_ROOT / "data")]
        if not full_scan:
            # The user's Snes9x 1.62.3 layout has validated root hints. Avoiding
            # a full process scan makes startup much faster and cooler.
            helper_args.append("--root-hints-only")
        self.spawned_helper = subprocess.Popen(
            helper_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        if not self.wait_connected(timeout):
            raise TimeoutError("C# Helper konnte sich nicht mit dem Probe-Server verbinden.")

    def wait_attached(self, timeout: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                tracker_status = self.latest_state.get("tracker_status", {})
                if isinstance(tracker_status, dict) and tracker_status.get("state") == "attached":
                    return True
                # A state payload also proves that the memory reader is ready.
                if any(key in self.latest_state for key in ("gold", "inventory", "characters")):
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)

    def close(self) -> None:
        self._running.clear()
        with self._condition:
            connection = self._connection
            self._connection = None
        for sock in (connection, self._listener):
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
        if self.spawned_helper and self.spawned_helper.poll() is None:
            self.spawned_helper.terminate()
            try:
                self.spawned_helper.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.spawned_helper.kill()


def create_bridge(args: argparse.Namespace):
    backend = getattr(args, "backend", "mesen")
    if backend == "mesen":
        return MesenFileBridge()
    if backend == "snes9x":
        return HelperBridge()
    raise ValueError(f"Unbekanntes Emulator-Backend: {backend}")


def backend_name(args: argparse.Namespace) -> str:
    return "Mesen" if getattr(args, "backend", "mesen") == "mesen" else "Snes9x"


def backend_attach_error(args: argparse.Namespace) -> str:
    if getattr(args, "backend", "mesen") == "mesen":
        return (
            "Keine aktive Mesen-Lua-Bridge gefunden. Öffne das Script Window, "
            f"lade '{LUA_SCRIPT}', aktiviere I/O/OS-Zugriff und starte mit F5."
        )
    return "Der Helper hat keine validierte Lufia-II-WRAM-Instanz gefunden."


def find_helper_executable() -> Optional[Path]:
    config_path = PROJECT_ROOT / "runtime_config.json"
    candidates: list[Path] = []
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            relative = config.get("helper", {}).get("relative_executable_path")
            if relative:
                candidates.append(PROJECT_ROOT / Path(relative))
        except (OSError, json.JSONDecodeError):
            pass
    candidates.extend(
        [
            PROJECT_ROOT
            / "emulator/csharp_helper/bin/Release/net8.0/win-x64/Lufia2AutoTracker.Helper.exe",
            PROJECT_ROOT
            / "emulator/csharp_helper/bin/Release/net8.0/win-x64/publish/Lufia2AutoTracker.Helper.exe",
        ]
    )
    return next((path.resolve() for path in candidates if path.exists()), None)


def _emulator_hwnd_and_pid(title_hint: str) -> tuple[Optional[int], Optional[int]]:
    if os.name != "nt":
        return None, None
    user32 = ctypes.windll.user32
    candidates: list[tuple[int, int, str]] = []
    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value
        if title_hint.lower() in title.lower():
            candidates.append((int(hwnd), pid.value, title))
        return True

    user32.EnumWindows(enum_proc_type(callback), 0)
    if candidates:
        hwnd, pid, _ = candidates[0]
        return hwnd, pid

    # Fullscreen emulators can have an empty title. Fall back to their PID.
    process_filter = "Mesen.exe" if "mesen" in title_hint.casefold() else "snes9x*.exe"
    try:
        import subprocess as _subprocess

        output = _subprocess.check_output(
            ["tasklist", "/FI", f"IMAGENAME eq {process_filter}", "/FO", "CSV", "/NH"],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        pids = {int(value) for value in re.findall(r'"(\d+)"', output)}
    except (OSError, ValueError, subprocess.SubprocessError):
        pids = set()
    if not pids:
        return None, None

    fallback: list[tuple[int, int]] = []

    def pid_callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids:
                fallback.append((int(hwnd), pid.value))
        return True

    user32.EnumWindows(enum_proc_type(pid_callback), 0)
    return fallback[0] if fallback else (None, None)


def focus_emulator(title_hint: str) -> None:
    if os.name != "nt":
        raise RuntimeError("Automatische Eingabe wird derzeit nur unter Windows unterstützt.")
    hwnd, target_pid = _emulator_hwnd_and_pid(title_hint)
    if not hwnd or not target_pid:
        raise RuntimeError(f"Kein sichtbares Emulatorfenster passend zu '{title_hint}' gefunden.")
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.2)
    foreground = user32.GetForegroundWindow()
    foreground_pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(foreground, ctypes.byref(foreground_pid))
    if foreground_pid.value != target_pid:
        raise RuntimeError(
            "Der Emulator konnte nicht sicher fokussiert werden; es wurden keine Tasten gesendet."
        )


def send_key_sequence(sequence: str, title_hint: str, duration: float) -> None:
    try:
        import pydirectinput
    except ImportError as exc:
        raise RuntimeError("pydirectinput fehlt. Installiere die requirements.txt.") from exc
    focus_emulator(title_hint)
    pydirectinput.PAUSE = 0.02
    for step in (part.strip().lower() for part in sequence.split(",")):
        if not step:
            continue
        buttons = [part.strip() for part in step.split("+")]
        unknown = [part for part in buttons if part not in SNES_KEY_MAP]
        if unknown:
            raise ValueError(f"Unbekannte SNES-Taste(n): {', '.join(unknown)}")
        keys = [SNES_KEY_MAP[part] for part in buttons]
        for key in keys:
            pydirectinput.keyDown(key)
        time.sleep(duration)
        for key in reversed(keys):
            pydirectinput.keyUp(key)
        time.sleep(0.08)


def load_runtime_title(backend: str = "snes9x") -> str:
    if backend == "mesen":
        return "Mesen"
    try:
        config = json.loads((PROJECT_ROOT / "runtime_config.json").read_text(encoding="utf-8"))
        return str(config.get("emulator", {}).get("window_title") or "Snes9x")
    except (OSError, json.JSONDecodeError):
        return "Snes9x"


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def capture(args: argparse.Namespace) -> int:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session = OUTPUT_ROOT / f"{timestamp}_{slugify(args.label)}"
    session.mkdir(parents=True, exist_ok=False)
    checklist_path = find_checklist()
    manifest = {
        "format_version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "label": args.label,
        "trials_requested": args.trials,
        "control_seconds": args.control_seconds,
        "settle_seconds": args.settle_seconds,
        "keys": args.keys,
        "backend": args.backend,
        "checklist": str(checklist_path.relative_to(PROJECT_ROOT)) if checklist_path else None,
        "trials": [],
    }
    write_json(session / "manifest.json", manifest)

    bridge = create_bridge(args)
    try:
        bridge.start()
        print(f"Warte auf {backend_name(args)} und die WRAM-Bridge ...")
        bridge.ensure_helper(full_scan=args.full_scan)
        if not bridge.wait_attached():
            raise TimeoutError(backend_attach_error(args))
        first_dump = bridge.dump()
        if len(first_dump) != WRAM_SIZE:
            raise RuntimeError(
                f"Helper liefert {len(first_dump)} Bytes statt 131072. "
                "Bitte den aktualisierten Helper neu bauen/starten."
            )
        print(f"Verbunden: vollständiger WRAM-Dump mit {len(first_dump)} Bytes.")
        print(f"Session: {session}")
        if args.keys:
            print(f"Automatische Aktion: {args.keys}")
        else:
            print("Manuell: Aktion erst nach der jeweiligen Aufforderung ausführen.")

        for trial_number in range(1, args.trials + 1):
            print(f"\nTrial {trial_number}/{args.trials}")
            if trial_number > 1 and args.pause_between:
                input("Ausgangszustand wiederherstellen, dann ENTER ... ")

            control_before = bridge.dump()
            time.sleep(args.control_seconds)
            before = bridge.dump()

            if args.keys:
                send_key_sequence(
                    args.keys,
                    load_runtime_title(args.backend),
                    args.key_duration,
                )
            else:
                input(f"Jetzt '{args.label}' ausführen; direkt danach ENTER ... ")

            time.sleep(args.settle_seconds)
            after = bridge.dump()

            prefix = f"trial_{trial_number:03d}"
            for suffix, data in (
                ("control_before.bin", control_before),
                ("before.bin", before),
                ("after.bin", after),
            ):
                (session / f"{prefix}_{suffix}").write_bytes(data)

            action_changes = sum(a != b for a, b in zip(before, after))
            control_changes = sum(a != b for a, b in zip(control_before, before))
            trial = {
                "number": trial_number,
                "captured_at": datetime.now().isoformat(timespec="milliseconds"),
                "control_before": f"{prefix}_control_before.bin",
                "before": f"{prefix}_before.bin",
                "after": f"{prefix}_after.bin",
                "control_changes": control_changes,
                "action_changes": action_changes,
                "state": dict(bridge.latest_state),
            }
            manifest["trials"].append(trial)
            write_json(session / "manifest.json", manifest)
            print(f"  Kontrolländerungen: {control_changes}, Aktionsänderungen: {action_changes}")

        analyze_session(
            session,
            top=args.top,
            expected_before=args.expected_before,
            expected_after=args.expected_after,
            expected_delta=args.expected_delta,
            widths=args.widths,
        )
        print(f"\nFertig. Kandidaten: {session / 'candidates.md'}")
        return 0
    finally:
        bridge.close()


def doctor(args: argparse.Namespace) -> int:
    bridge = create_bridge(args)
    try:
        bridge.start()
        print(f"Warte auf {backend_name(args)} und eine gültige Lufia-II-Instanz ...")
        bridge.ensure_helper(full_scan=args.full_scan)
        if not bridge.wait_attached():
            raise TimeoutError(backend_attach_error(args))
        dump = bridge.dump()
        if len(dump) != WRAM_SIZE:
            raise RuntimeError(f"Dumpgröße {len(dump)} statt {WRAM_SIZE} Bytes.")
        gold = int.from_bytes(dump[0x0A8A:0x0A8D], "little")
        map_value = int.from_bytes(dump[0x120A:0x120C], "little")
        save_cursor = dump[SAVE_CURSOR_OFFSET : SAVE_CURSOR_OFFSET + 2]
        save_cursor_label = SAVE_CURSOR_VALUES.get(save_cursor, "nicht zugeordnet")
        profile = bridge.latest_state.get("tracker_status", {}).get(
            "profile",
            bridge.latest_state.get("backend", "?"),
        )
        print("LIVE-OK")
        print(f"  Profil: {profile}")
        print(f"  WRAM: {len(dump)} Bytes (7E:0000-7F:FFFF)")
        print(f"  SHA-256: {hashlib.sha256(dump).hexdigest()[:16]}")
        print(f"  Gold-Kandidat @ 7E:0A8A: {gold}")
        print(f"  Map-Kandidat @ 7E:120A: {map_value}")
        print(
            f"  Save-Cursor @ 7E:{SAVE_CURSOR_OFFSET:04X}-"
            f"{SAVE_CURSOR_OFFSET + 1:04X}: "
            f"{save_cursor.hex(' ').upper()} ({save_cursor_label})"
        )
        return 0
    finally:
        bridge.close()


def _hotkey_pressed(user32, main_key: int) -> bool:
    return (
        bool(user32.GetAsyncKeyState(0x11) & 0x8000)  # Ctrl
        and bool(user32.GetAsyncKeyState(0x10) & 0x8000)  # Shift
        and bool(user32.GetAsyncKeyState(main_key) & 0x8000)
    )


def _beep(pattern: str) -> None:
    try:
        import winsound

        patterns = {
            "ready": [(900, 140)],
            "saved": [(1200, 90), (1550, 110)],
            "done": [(900, 80), (1200, 80), (1600, 150)],
            "error": [(350, 250)],
        }
        for frequency, duration in patterns[pattern]:
            winsound.Beep(frequency, duration)
    except (ImportError, RuntimeError):
        pass


def record(args: argparse.Namespace) -> int:
    if os.name != "nt":
        raise RuntimeError("Der Hotkey-Recorder wird derzeit nur unter Windows unterstützt.")

    label = args.label or input("Was soll aufgezeichnet werden? ").strip()
    if not label:
        raise ValueError("Eine kurze Bezeichnung ist erforderlich.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session = OUTPUT_ROOT / f"{timestamp}_{slugify(label)}"
    session.mkdir(parents=True, exist_ok=False)
    checklist_path = find_checklist()
    manifest = {
        "format_version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "trials_requested": args.trials,
        "control_seconds": args.control_seconds,
        "settle_seconds": args.settle_seconds,
        "backend": args.backend,
        "keys": None,
        "checklist": str(checklist_path.relative_to(PROJECT_ROOT)) if checklist_path else None,
        "trials": [],
    }
    write_json(session / "manifest.json", manifest)

    bridge = create_bridge(args)
    try:
        bridge.start()
        print(f"Verbinde mit {backend_name(args)} ...")
        bridge.ensure_helper(full_scan=args.full_scan)
        if not bridge.wait_attached():
            raise TimeoutError(backend_attach_error(args))
        if len(bridge.dump()) != WRAM_SIZE:
            raise RuntimeError("Der Helper liefert keinen vollständigen 128-KiB-Dump.")

        print()
        print(f"Aufzeichnung: {label}")
        print("  Ctrl+Shift+1  Vorher-Messung vorbereiten")
        print("  ein Ton        Jetzt die Aktion im Spiel ausführen")
        print("  Ctrl+Shift+2  Nachher-Messung speichern")
        print("  Ctrl+Shift+0  Vorzeitig beenden und auswerten")
        print(f"Nach {args.trials} Wiederholungen wird automatisch ausgewertet.")
        print(f"Du kannst jetzt zu {backend_name(args)} wechseln.")
        _beep("ready")

        user32 = ctypes.windll.user32
        armed: Optional[tuple[bytes, bytes]] = None
        latch = False
        trial_number = 1

        while True:
            before_hotkey = _hotkey_pressed(user32, 0x31)  # 1
            after_hotkey = _hotkey_pressed(user32, 0x32)  # 2
            finish_hotkey = _hotkey_pressed(user32, 0x30)  # 0
            any_hotkey = before_hotkey or after_hotkey or finish_hotkey

            if any_hotkey and not latch:
                latch = True
                if finish_hotkey:
                    break
                if before_hotkey:
                    if armed is not None:
                        print("Vorher-Messung ist bereits bereit; jetzt Ctrl+Shift+2 drücken.")
                        _beep("error")
                    else:
                        print(f"Trial {trial_number}: Kontrollfenster ...", flush=True)
                        control_before = bridge.dump()
                        time.sleep(args.control_seconds)
                        before = bridge.dump()
                        armed = (control_before, before)
                        print("  BEREIT: Aktion ausführen, danach Ctrl+Shift+2.", flush=True)
                        _beep("ready")
                elif after_hotkey:
                    if armed is None:
                        print("Zuerst Ctrl+Shift+1 drücken.")
                        _beep("error")
                    else:
                        time.sleep(args.settle_seconds)
                        after = bridge.dump()
                        control_before, before = armed
                        prefix = f"trial_{trial_number:03d}"
                        for suffix, data in (
                            ("control_before.bin", control_before),
                            ("before.bin", before),
                            ("after.bin", after),
                        ):
                            (session / f"{prefix}_{suffix}").write_bytes(data)

                        action_changes = sum(a != b for a, b in zip(before, after))
                        control_changes = sum(a != b for a, b in zip(control_before, before))
                        manifest["trials"].append(
                            {
                                "number": trial_number,
                                "captured_at": datetime.now().isoformat(timespec="milliseconds"),
                                "control_before": f"{prefix}_control_before.bin",
                                "before": f"{prefix}_before.bin",
                                "after": f"{prefix}_after.bin",
                                "control_changes": control_changes,
                                "action_changes": action_changes,
                                "state": dict(bridge.latest_state),
                            }
                        )
                        write_json(session / "manifest.json", manifest)
                        print(
                            f"  GESPEICHERT: {action_changes} Aktionsänderungen, "
                            f"{control_changes} Kontrolländerungen.",
                            flush=True,
                        )
                        _beep("saved")
                        armed = None
                        trial_number += 1
                        if trial_number > args.trials:
                            break
            elif not any_hotkey:
                latch = False

            # GetAsyncKeyState polling must never become a busy loop.
            time.sleep(0.04)

        if armed is not None:
            print("Unvollständige Vorher-Messung wurde verworfen.")
        if not manifest["trials"]:
            print("Keine vollständige Wiederholung gespeichert.")
            return 0

        analyze_session(session, top=args.top)
        _beep("done")
        print(f"Fertig: {session / 'candidates.md'}")
        return 0
    finally:
        bridge.close()


def record_lifecycle(args: argparse.Namespace) -> int:
    """Record a reversible state as closed -> open -> held open -> closed."""
    if os.name != "nt":
        raise RuntimeError("Der Hotkey-Recorder wird derzeit nur unter Windows unterstützt.")

    label = args.label or input("Welcher Zustand soll aufgezeichnet werden? ").strip()
    if not label:
        raise ValueError("Eine kurze Bezeichnung ist erforderlich.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session = OUTPUT_ROOT / f"{timestamp}_{slugify(label)}_lifecycle"
    session.mkdir(parents=True, exist_ok=False)
    checklist_path = find_checklist()
    manifest = {
        "format_version": 2,
        "experiment_type": "lifecycle",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "backend": args.backend,
        "trials_requested": args.trials,
        "checklist": str(checklist_path.relative_to(PROJECT_ROOT)) if checklist_path else None,
        "trials": [],
    }
    write_json(session / "manifest.json", manifest)

    bridge = create_bridge(args)
    try:
        bridge.start()
        print(f"Verbinde mit {backend_name(args)} ...")
        bridge.ensure_helper(full_scan=args.full_scan)
        if not bridge.wait_attached():
            raise TimeoutError(backend_attach_error(args))
        if len(bridge.dump()) != WRAM_SIZE:
            raise RuntimeError("Der Helper liefert keinen vollständigen 128-KiB-Dump.")

        stages = (
            ("closed_before", "Zustand geschlossen/aus"),
            ("open", "Zustand vollständig geöffnet/ein"),
            ("open_stable", "Zustand unverändert weiterhin geöffnet/ein"),
            ("closed_after", "Zustand wieder vollständig geschlossen/aus"),
        )
        print()
        print(f"Lifecycle-Aufzeichnung: {label}")
        print("Pro Wiederholung denselben Zustand öffnen, kurz halten und wieder schließen:")
        for number, (_, description) in enumerate(stages, 1):
            print(f"  Ctrl+Shift+{number}  {description}")
        print("  Ctrl+Shift+0  Vorzeitig beenden und auswerten")
        print("Zwischen 2 und 3 nichts im Spiel auslösen; nur kurz warten.")
        print(f"Nach {args.trials} Wiederholungen wird automatisch ausgewertet.")
        print(f"Du kannst jetzt zu {backend_name(args)} wechseln.")
        _beep("ready")

        user32 = ctypes.windll.user32
        stage_index = 0
        snapshots: dict[str, bytes] = {}
        latch = False
        trial_number = 1

        while True:
            pressed = {
                number: _hotkey_pressed(user32, 0x30 + number)
                for number in range(1, 5)
            }
            finish_hotkey = _hotkey_pressed(user32, 0x30)
            any_hotkey = finish_hotkey or any(pressed.values())

            if any_hotkey and not latch:
                latch = True
                if finish_hotkey:
                    break

                pressed_number = next((number for number, active in pressed.items() if active), None)
                expected_number = stage_index + 1
                if pressed_number != expected_number:
                    print(f"Erwartet wird jetzt Ctrl+Shift+{expected_number}.")
                    _beep("error")
                    continue

                field, description = stages[stage_index]
                snapshots[field] = bridge.dump()
                print(f"Trial {trial_number}: {description} gespeichert.", flush=True)
                stage_index += 1
                _beep("ready" if stage_index < len(stages) else "saved")

                if stage_index == len(stages):
                    prefix = f"trial_{trial_number:03d}"
                    trial_entry = {
                        "number": trial_number,
                        "captured_at": datetime.now().isoformat(timespec="milliseconds"),
                        "state": dict(bridge.latest_state),
                    }
                    for field, _ in stages:
                        filename = f"{prefix}_{field}.bin"
                        (session / filename).write_bytes(snapshots[field])
                        trial_entry[field] = filename
                    manifest["trials"].append(trial_entry)
                    write_json(session / "manifest.json", manifest)
                    snapshots = {}
                    stage_index = 0
                    trial_number += 1
                    if trial_number > args.trials:
                        break
                    print(f"Bereit für Trial {trial_number}: wieder bei Ctrl+Shift+1 beginnen.")
            elif not any_hotkey:
                latch = False

            time.sleep(0.04)

        if snapshots:
            print("Unvollständige Lifecycle-Wiederholung wurde verworfen.")
        if not manifest["trials"]:
            print("Keine vollständige Wiederholung gespeichert.")
            return 0

        analyze_lifecycle_session(session, top=args.top)
        _beep("done")
        print(f"Fertig: {session / 'candidates.md'}")
        return 0
    finally:
        bridge.close()


def read_trials(session: Path) -> tuple[dict, list[tuple[bytes, bytes, bytes]]]:
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    trials = []
    for trial in manifest.get("trials", []):
        control = (session / trial["control_before"]).read_bytes()
        before = (session / trial["before"]).read_bytes()
        after = (session / trial["after"]).read_bytes()
        if len({len(control), len(before), len(after)}) != 1:
            raise ValueError(f"Unterschiedliche Dumpgrößen in Trial {trial.get('number')}.")
        trials.append((control, before, after))
    if not trials:
        raise ValueError("Die Session enthält keine vollständigen Trials.")
    return manifest, trials


def read_lifecycle_trials(
    session: Path,
) -> tuple[dict, list[tuple[bytes, bytes, bytes, bytes]]]:
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    trials = []
    fields = ("closed_before", "open", "open_stable", "closed_after")
    for trial in manifest.get("trials", []):
        dumps = tuple((session / trial[field]).read_bytes() for field in fields)
        if len({len(dump) for dump in dumps}) != 1:
            raise ValueError(f"Unterschiedliche Dumpgrößen in Trial {trial.get('number')}.")
        trials.append(dumps)
    if not trials:
        raise ValueError("Die Session enthält keine vollständigen Lifecycle-Trials.")
    return manifest, trials


def _numeric_matches(
    trials: list[tuple[bytes, bytes, bytes]],
    widths: Iterable[int],
    expected_before: Optional[int],
    expected_after: Optional[int],
    expected_delta: Optional[int],
) -> list[dict]:
    if expected_before is None and expected_after is None and expected_delta is None:
        return []
    results = []
    size = len(trials[0][0])
    for width in widths:
        if width not in (1, 2, 3, 4):
            raise ValueError("Breiten müssen 1, 2, 3 oder 4 Bytes sein.")
        for offset in range(0, size - width + 1):
            hits = 0
            quiet = 0
            samples = []
            for control, before, after in trials:
                cval = int.from_bytes(control[offset : offset + width], "little")
                bval = int.from_bytes(before[offset : offset + width], "little")
                aval = int.from_bytes(after[offset : offset + width], "little")
                matches = (
                    (expected_before is None or bval == expected_before)
                    and (expected_after is None or aval == expected_after)
                    and (expected_delta is None or aval - bval == expected_delta)
                )
                hits += int(matches)
                quiet += int(cval == bval)
                samples.append((bval, aval))
            if hits:
                results.append(
                    {
                        "offset": offset,
                        "address": bus_address(offset),
                        "width": width,
                        "hits": hits,
                        "trials": len(trials),
                        "control_quiet": quiet,
                        "samples": [f"{before}->{after}" for before, after in samples],
                    }
                )
    results.sort(key=lambda row: (-row["hits"], -row["control_quiet"], row["width"], row["offset"]))
    return results


def _motion_hint(label: str) -> Optional[tuple[str, int, str]]:
    normalized = label.casefold()
    directions = (
        (("runter", "down", "süd", "south"), "Y", 1, "Runter: Y steigt"),
        (("hoch", "up", "nord", "north"), "Y", -1, "Hoch: Y fällt"),
        (("rechts", "right", "ost", "east"), "X", 1, "Rechts: X steigt"),
        (("links", "left", "west"), "X", -1, "Links: X fällt"),
    )
    for words, axis, sign, description in directions:
        if any(word in normalized for word in words):
            return axis, sign, description
    return None


def _motion_matches(
    trials: list[tuple[bytes, bytes, bytes]],
    checklist: ChecklistIndex,
    label: str,
) -> tuple[Optional[str], list[dict]]:
    hint = _motion_hint(label)
    if hint is None:
        return None, []

    axis, direction, description = hint
    count = len(trials)
    minimum_hits = max(2, (4 * count + 4) // 5)
    matches = []
    size = len(trials[0][0])

    for offset in range(size):
        direction_hits = 0
        quiet = 0
        deltas = []
        samples = []
        for control, before, after in trials:
            cval = control[offset]
            bval = before[offset]
            aval = after[offset]
            quiet += int(cval == bval)
            delta = aval - bval
            if delta and delta * direction > 0 and abs(delta) <= 0x40:
                direction_hits += 1
                deltas.append(delta)
            samples.append(f"{bval:02X}->{aval:02X}")

        if direction_hits < minimum_hits or quiet < minimum_hits:
            continue
        status, checklist_label = checklist.describe(offset)
        folded_label = checklist_label.casefold()
        axis_match = int(
            f"spieler-{axis.casefold()}" in folded_label
            or f"{axis.casefold()}-position" in folded_label
            or f"{axis.casefold()} lokal" in folded_label
            or f"stadt-{axis.casefold()}" in folded_label
        )
        delta_consistency = Counter(deltas).most_common(1)[0][1] / len(deltas)
        score = (
            100.0 * direction_hits / count
            + 50.0 * quiet / count
            + 100.0 * axis_match
            + 10.0 * delta_consistency
        )
        matches.append(
            {
                "offset": offset,
                "address": bus_address(offset),
                "score": round(score, 2),
                "direction_hits": direction_hits,
                "trials": count,
                "control_quiet": quiet,
                "axis_match": bool(axis_match),
                "checklist_status": status,
                "checklist_label": checklist_label,
                "deltas": ", ".join(
                    f"{delta:+d} x{amount}"
                    for delta, amount in Counter(deltas).most_common(4)
                ),
                "samples": ", ".join(samples),
            }
        )

    matches.sort(
        key=lambda row: (
            -row["axis_match"],
            -row["score"],
            -int(bool(row["checklist_label"])),
            row["offset"],
        )
    )
    return description, matches


def analyze_lifecycle_session(session: Path, top: int = 100) -> list[dict]:
    session = session.resolve()
    manifest, trials = read_lifecycle_trials(session)
    checklist = ChecklistIndex(find_checklist())
    count = len(trials)
    size = len(trials[0][0])
    rows = []

    for offset in range(size):
        open_hits = 0
        stable_hits = 0
        return_hits = 0
        transitions: Counter[tuple[int, int]] = Counter()
        for closed_before, opened, open_stable, closed_after in trials:
            if closed_before[offset] != opened[offset]:
                open_hits += 1
                transitions[(closed_before[offset], opened[offset])] += 1
            if opened[offset] == open_stable[offset]:
                stable_hits += 1
            if closed_before[offset] == closed_after[offset]:
                return_hits += 1

        if not open_hits:
            continue
        transition_consistency = max(transitions.values()) / open_hits
        score = (
            100.0
            * (open_hits / count)
            * (stable_hits / count)
            * (return_hits / count)
            * (0.8 + 0.2 * transition_consistency)
        )
        status, label = checklist.describe(offset)
        rows.append(
            {
                "offset": offset,
                "address": bus_address(offset),
                "score": round(score, 2),
                "open_hits": open_hits,
                "stable_hits": stable_hits,
                "return_hits": return_hits,
                "trials": count,
                "consistency": round(transition_consistency, 3),
                "checklist_status": status,
                "checklist_label": label,
                "transitions": ", ".join(
                    f"{old:02X}->{new:02X} x{amount}"
                    for (old, new), amount in transitions.most_common(4)
                ),
            }
        )

    rows.sort(
        key=lambda row: (
            -row["score"],
            -row["open_hits"],
            -row["stable_hits"],
            -row["return_hits"],
            row["offset"],
        )
    )
    report = {
        "format_version": 2,
        "experiment_type": "lifecycle",
        "session": str(session),
        "label": manifest.get("label"),
        "wram_bytes": size,
        "trial_count": count,
        "candidate_count": len(rows),
        "candidates": rows,
    }
    write_json(session / "candidates.json", report)

    fieldnames = [
        "offset",
        "address",
        "score",
        "open_hits",
        "stable_hits",
        "return_hits",
        "trials",
        "consistency",
        "checklist_status",
        "checklist_label",
        "transitions",
    ]
    with (session / "candidates.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    def markdown_cell(value: object) -> str:
        return str(value).replace("|", r"\|").replace("\n", " ")

    lines = [
        f"# WRAM lifecycle candidates: {manifest.get('label', session.name)}",
        "",
        f"- Trials: {count}",
        "- Muster: geschlossen -> offen -> stabil offen -> wieder geschlossen",
        "- Ein hoher Score bevorzugt reversible Zustandswerte und verwirft laufende Folgedaten.",
        "",
        "| Rank | Address | Score | Öffnet | Stabil | Kehrt zurück | Checklist | Transitions |",
        "|---:|---|---:|---:|---:|---:|---|---|",
    ]
    for rank, row in enumerate(rows[:top], 1):
        checklist_text = (
            f"[{row['checklist_status']}] {row['checklist_label']}"
            if row["checklist_label"]
            else "unmentioned"
        )
        lines.append(
            f"| {rank} | {row['address']} | {row['score']:.2f} | "
            f"{row['open_hits']}/{row['trials']} | "
            f"{row['stable_hits']}/{row['trials']} | "
            f"{row['return_hits']}/{row['trials']} | "
            f"{markdown_cell(checklist_text)} | {markdown_cell(row['transitions'])} |"
        )
    (session / "candidates.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Lifecycle-Analyse: {len(rows)} beim Öffnen geänderte Adressen.")
    return rows


def compare_sessions(
    sessions: Iterable[Path],
    min_score: float = 80.0,
    output: Optional[Path] = None,
) -> Path:
    session_paths = [session.resolve() for session in sessions]
    if len(session_paths) < 2:
        raise ValueError("Für einen Kampagnenvergleich sind mindestens zwei Sessions nötig.")

    reports = []
    for session in session_paths:
        report_path = session / "candidates.json"
        if not report_path.exists():
            analyze_session(session)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        candidates = {
            int(row["offset"]): row
            for row in report.get("candidates", [])
            if float(row.get("score", 0)) >= min_score
        }
        reports.append((session, report, candidates))

    common_offsets = set(reports[0][2])
    for _, _, candidates in reports[1:]:
        common_offsets &= set(candidates)

    rows = []
    for offset in common_offsets:
        occurrences = []
        labels = []
        for session, report, candidates in reports:
            candidate = candidates[offset]
            checklist_label = candidate.get("checklist_label", "")
            if checklist_label:
                labels.append(checklist_label)
            occurrences.append(
                {
                    "session": str(session),
                    "label": report.get("label", session.name),
                    "score": float(candidate.get("score", 0)),
                    "transitions": candidate.get("transitions", ""),
                }
            )
        rows.append(
            {
                "offset": offset,
                "address": bus_address(offset),
                "average_score": round(
                    sum(item["score"] for item in occurrences) / len(occurrences),
                    2,
                ),
                "checklist_label": " | ".join(dict.fromkeys(labels)),
                "sessions": occurrences,
            }
        )

    rows.sort(
        key=lambda row: (
            -int(bool(row["checklist_label"])),
            -row["average_score"],
            row["offset"],
        )
    )
    if output is None:
        report_dir = Path(__file__).resolve().parent / "campaign_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        combined_label = "_".join(
            slugify(str(report.get("label", session.name)))
            for session, report, _ in reports[:3]
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = report_dir / f"{timestamp}_{combined_label}.md"
    else:
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.suffix.casefold() != ".md":
            output = output.with_suffix(".md")

    def markdown_cell(value: object) -> str:
        return str(value).replace("|", r"\|").replace("\n", " ")

    lines = [
        "# WRAM campaign comparison",
        "",
        f"- Sessions: {len(reports)}",
        f"- Minimum score per session: {min_score:.2f}",
        f"- Common candidates: {len(rows)}",
        "",
        "Nur Adressen, die den Mindestscore in jeder Session erreichen, erscheinen hier.",
        "",
        "| Rank | Address | Average | Checklist | Per session |",
        "|---:|---|---:|---|---|",
    ]
    for rank, row in enumerate(rows, 1):
        details = "; ".join(
            f"{item['label']}: {item['score']:.2f} ({item['transitions'] or 'no transition summary'})"
            for item in row["sessions"]
        )
        lines.append(
            f"| {rank} | {row['address']} | {row['average_score']:.2f} | "
            f"{markdown_cell(row['checklist_label'] or 'unmentioned')} | "
            f"{markdown_cell(details)} |"
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(
        output.with_suffix(".json"),
        {
            "format_version": 1,
            "minimum_score": min_score,
            "sessions": [str(session) for session, _, _ in reports],
            "candidate_count": len(rows),
            "candidates": rows,
        },
    )
    print(f"Kampagnenvergleich: {len(rows)} gemeinsame Kandidaten.")
    return output


def analyze_session(
    session: Path,
    top: int = 100,
    expected_before: Optional[int] = None,
    expected_after: Optional[int] = None,
    expected_delta: Optional[int] = None,
    widths: Iterable[int] = (1, 2, 3, 4),
) -> list[dict]:
    session = session.resolve()
    manifest_preview = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    if manifest_preview.get("experiment_type") == "lifecycle":
        return analyze_lifecycle_session(session, top=top)
    manifest, trials = read_trials(session)
    checklist = ChecklistIndex(find_checklist())
    count = len(trials)
    size = len(trials[0][0])
    rows = []

    for offset in range(size):
        action_hits = 0
        control_hits = 0
        transitions: Counter[tuple[int, int]] = Counter()
        for control, before, after in trials:
            if control[offset] != before[offset]:
                control_hits += 1
            if before[offset] != after[offset]:
                action_hits += 1
                transitions[(before[offset], after[offset])] += 1
        if not action_hits:
            continue
        hit_rate = action_hits / count
        control_rate = control_hits / count
        consistency = max(transitions.values()) / action_hits
        score = 100.0 * hit_rate * (1.0 - control_rate) * (0.75 + 0.25 * consistency)
        status, label = checklist.describe(offset)
        transition_text = ", ".join(
            f"{old:02X}->{new:02X} x{amount}"
            for (old, new), amount in transitions.most_common(4)
        )
        rows.append(
            {
                "offset": offset,
                "address": bus_address(offset),
                "score": round(score, 2),
                "action_hits": action_hits,
                "trials": count,
                "control_hits": control_hits,
                "consistency": round(consistency, 3),
                "checklist_status": status,
                "checklist_label": label,
                "transitions": transition_text,
            }
        )

    rows.sort(
        key=lambda row: (
            -row["score"],
            row["control_hits"],
            -row["action_hits"],
            row["offset"],
        )
    )
    numeric = _numeric_matches(
        trials,
        widths,
        expected_before,
        expected_after,
        expected_delta,
    )
    motion_description, motion = _motion_matches(
        trials,
        checklist,
        str(manifest.get("label", "")),
    )
    report = {
        "format_version": 1,
        "session": str(session),
        "label": manifest.get("label"),
        "wram_bytes": size,
        "trial_count": count,
        "candidate_count": len(rows),
        "candidates": rows,
        "numeric_matches": numeric,
        "motion_description": motion_description,
        "motion_candidates": motion,
    }
    write_json(session / "candidates.json", report)

    with (session / "candidates.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fieldnames = list(rows[0].keys()) if rows else [
            "offset",
            "address",
            "score",
            "action_hits",
            "trials",
            "control_hits",
            "consistency",
            "checklist_status",
            "checklist_label",
            "transitions",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    session_stems = {
        word[:4].casefold()
        for word in re.findall(r"[^\W_]+", str(manifest.get("label", "")), re.UNICODE)
        if len(word) >= 4
    }

    def checklist_relevance(row: dict) -> int:
        label_stems = {
            word[:4].casefold()
            for word in re.findall(r"[^\W_]+", row["checklist_label"], re.UNICODE)
            if len(word) >= 4
        }
        return int(bool(session_stems & label_stems))

    def markdown_cell(value: object) -> str:
        return str(value).replace("|", r"\|").replace("\n", " ")

    known_rows = sorted(
        (row for row in rows if row["checklist_label"]),
        key=lambda row: (
            -checklist_relevance(row),
            -row["action_hits"],
            row["control_hits"],
            -row["score"],
            row["offset"],
        ),
    )
    lines = [
        f"# WRAM candidates: {manifest.get('label', session.name)}",
        "",
        f"- Trials: {count}",
        f"- WRAM: {size} bytes",
        "- Score: repeatable action changes, discounted by control-window noise",
    ]
    if len(rows) >= 2000:
        lines.append(
            f"- Hinweis: {len(rows)} geänderte Adressen deuten auf einen großen "
            "Bildschirm-/Textzustandswechsel. Für den eigentlichen Zustandswert "
            "ist eine Lifecycle-Aufnahme geeigneter."
        )
    lines.append("")
    if motion:
        lines.extend(
            [
                f"## Richtungsanalyse ({motion_description})",
                "",
                "Diese Bytes folgen in mindestens 80 % der Wiederholungen der erwarteten "
                "Richtung und bleiben im Kontrollfenster ruhig:",
                "",
                "| Address | Score | Richtung | Control | Checklist | Deltas |",
                "|---|---:|---:|---:|---|---|",
            ]
        )
        for row in motion[: min(top, 30)]:
            motion_checklist_text = (
                f"[{row['checklist_status']}] {row['checklist_label']}"
                if row["checklist_label"]
                else "unmentioned"
            )
            lines.append(
                f"| {row['address']} | {row['score']:.2f} | "
                f"{row['direction_hits']}/{row['trials']} | "
                f"{row['control_quiet']}/{row['trials']} | "
                f"{markdown_cell(motion_checklist_text)} | {markdown_cell(row['deltas'])} |"
            )
        lines.append("")

    if known_rows:
        lines.extend(
            [
                "## Bereits in der Checkliste gepflegte Treffer",
                "",
                "Diese bereits gepflegten Adressen änderten sich zeitgleich. "
                "Das bestätigt Korrelation, nicht automatisch die Ursache:",
                "",
                "| Address | Score | Action | Control | Checklist | Transitions |",
                "|---|---:|---:|---:|---|---|",
            ]
        )
        for row in known_rows[:top]:
            known_checklist_text = f"[{row['checklist_status']}] {row['checklist_label']}"
            lines.append(
                f"| {row['address']} | {row['score']:.2f} | "
                f"{row['action_hits']}/{row['trials']} | {row['control_hits']}/{row['trials']} | "
                f"{markdown_cell(known_checklist_text)} | "
                f"{markdown_cell(row['transitions'])} |"
            )
        lines.extend(["", "## Alle Kandidaten", ""])

    lines.extend(
        [
        "| Rank | Address | Score | Action | Control | Checklist | Transitions |",
        "|---:|---|---:|---:|---:|---|---|",
        ]
    )
    for rank, row in enumerate(rows[:top], 1):
        checklist_text = (
            f"[{row['checklist_status']}] {row['checklist_label']}"
            if row["checklist_label"]
            else "unmentioned"
        )
        lines.append(
            f"| {rank} | {row['address']} | {row['score']:.2f} | "
            f"{row['action_hits']}/{row['trials']} | {row['control_hits']}/{row['trials']} | "
            f"{markdown_cell(checklist_text)} | {markdown_cell(row['transitions'])} |"
        )
    if numeric:
        lines.extend(
            [
                "",
                "## Numeric matches",
                "",
                "| Address | Width | Hits | Control quiet | Samples |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for row in numeric[:top]:
            lines.append(
                f"| {row['address']} | {row['width']} | {row['hits']}/{row['trials']} | "
                f"{row['control_quiet']}/{row['trials']} | {', '.join(row['samples'])} |"
            )
    (session / "candidates.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Analyse: {len(rows)} geänderte Adressen, {len(numeric)} numerische Treffer.")
    return rows


def parse_int(value: str) -> int:
    return int(value, 0)


def parse_widths(value: str) -> tuple[int, ...]:
    return tuple(int(part.strip()) for part in value.split(",") if part.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wiederholbare WRAM-Diffs mit Aktions-/Kontrollkorrelation."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser(
        "doctor", help="Helper-Anbindung und vollständigen Live-Dump prüfen."
    )
    doctor_parser.add_argument(
        "--backend",
        choices=("mesen", "snes9x"),
        default="mesen",
        help="Emulator-Backend (Standard: mesen).",
    )
    doctor_parser.add_argument(
        "--full-scan",
        action="store_true",
        help="Teure dynamische Prozesssuche statt validierter Snes9x-Root-Hinweise.",
    )
    doctor_parser.set_defaults(func=doctor)

    record_parser = subparsers.add_parser(
        "record", help="Einfache Aufzeichnung über globale Hotkeys."
    )
    record_parser.add_argument("--label", help="Aktionsname; wird sonst einmal abgefragt.")
    record_parser.add_argument("--trials", type=int, default=5)
    record_parser.add_argument("--control-seconds", type=float, default=0.5)
    record_parser.add_argument("--settle-seconds", type=float, default=0.05)
    record_parser.add_argument("--top", type=int, default=100)
    record_parser.add_argument("--full-scan", action="store_true")
    record_parser.add_argument(
        "--backend",
        choices=("mesen", "snes9x"),
        default="mesen",
    )
    record_parser.set_defaults(func=record)

    lifecycle_parser = subparsers.add_parser(
        "lifecycle",
        help="Reversiblen Zustand als geschlossen/offen/stabil/geschlossen aufnehmen.",
    )
    lifecycle_parser.add_argument("--label", help="Zustandsname; wird sonst einmal abgefragt.")
    lifecycle_parser.add_argument("--trials", type=int, default=5)
    lifecycle_parser.add_argument("--top", type=int, default=100)
    lifecycle_parser.add_argument("--full-scan", action="store_true")
    lifecycle_parser.add_argument(
        "--backend",
        choices=("mesen", "snes9x"),
        default="mesen",
    )
    lifecycle_parser.set_defaults(func=record_lifecycle)

    capture_parser = subparsers.add_parser("capture", help="Neue Live-Session aufnehmen.")
    capture_parser.add_argument("--label", required=True, help="Semantischer Aktionsname.")
    capture_parser.add_argument("--trials", type=int, default=5, help="Anzahl Wiederholungen.")
    capture_parser.add_argument(
        "--keys",
        help="Optionale SNES-Tastenfolge, z.B. 'down,a' oder 'down+a'. Ohne Wert manuell.",
    )
    capture_parser.add_argument("--control-seconds", type=float, default=0.5)
    capture_parser.add_argument("--settle-seconds", type=float, default=0.25)
    capture_parser.add_argument("--key-duration", type=float, default=0.12)
    capture_parser.add_argument(
        "--pause-between",
        action="store_true",
        help="Vor jedem weiteren Trial auf manuelles Zurücksetzen warten.",
    )
    capture_parser.add_argument("--top", type=int, default=100)
    capture_parser.add_argument("--expected-before", type=parse_int)
    capture_parser.add_argument("--expected-after", type=parse_int)
    capture_parser.add_argument("--expected-delta", type=parse_int)
    capture_parser.add_argument("--widths", type=parse_widths, default=(1, 2, 3, 4))
    capture_parser.add_argument("--full-scan", action="store_true")
    capture_parser.add_argument(
        "--backend",
        choices=("mesen", "snes9x"),
        default="mesen",
    )
    capture_parser.set_defaults(func=capture)

    analyze_parser = subparsers.add_parser("analyze", help="Gespeicherte Session neu analysieren.")
    analyze_parser.add_argument("session", type=Path)
    analyze_parser.add_argument("--top", type=int, default=100)
    analyze_parser.add_argument("--expected-before", type=parse_int)
    analyze_parser.add_argument("--expected-after", type=parse_int)
    analyze_parser.add_argument("--expected-delta", type=parse_int)
    analyze_parser.add_argument("--widths", type=parse_widths, default=(1, 2, 3, 4))

    def analyze_command(args: argparse.Namespace) -> int:
        analyze_session(
            args.session,
            top=args.top,
            expected_before=args.expected_before,
            expected_after=args.expected_after,
            expected_delta=args.expected_delta,
            widths=args.widths,
        )
        print(f"Kandidaten: {args.session.resolve() / 'candidates.md'}")
        return 0

    analyze_parser.set_defaults(func=analyze_command)

    compare_parser = subparsers.add_parser(
        "compare",
        help="Gemeinsame Kandidaten aus mehreren ähnlichen Sessions bilden.",
    )
    compare_parser.add_argument("sessions", type=Path, nargs="+")
    compare_parser.add_argument("--min-score", type=float, default=80.0)
    compare_parser.add_argument("--output", type=Path)

    def compare_command(args: argparse.Namespace) -> int:
        result = compare_sessions(
            args.sessions,
            min_score=args.min_score,
            output=args.output,
        )
        print(f"Report: {result}")
        return 0

    compare_parser.set_defaults(func=compare_command)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    if argv is None and len(sys.argv) == 1:
        argv = ["record"]
    args = parser.parse_args(argv)
    if getattr(args, "trials", 1) < 1:
        parser.error("--trials muss mindestens 1 sein.")
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
