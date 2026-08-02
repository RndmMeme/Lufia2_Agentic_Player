"""
WRAM Discovery Agent v1.1 - Vollautomatische WRAM-Adress-Ermittlung
====================================================================
STARTET einen TCP-SERVER (Port 64321) und startet dann den C# Helper.
Der C# Helper verbindet sich als Client.
Sendet DUMP-Kommandos, berechnet Diffs zwischen Vorher/Nachher-Dumps.
Alle Ergebnisse landen in wram_discovery/ - KEINE Aenderungen an bestehenden Dateien.
"""

import socket
import json
import logging
import os
import time
import sys
import re
import threading
import subprocess
import atexit
from pathlib import Path
from typing import Dict, List, Optional, Any

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "discovery.log"), mode="w"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

WRAM_SIZE = 0x20000
HOST = "127.0.0.1"
PORT = 64321
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(OUTPUT_DIR, "snapshots")
WRAM_BASE_KNOWN = 0x7E0000

# ========================================================================
# BEKANNTE OFFSETS (AUS ram_map.json + dungeon_flags)
# ========================================================================
KNOWN_OFFSETS: Dict[int, str] = {
    0x3586: "DungeonBlocking",
    0x2CB5: "FacingDirectionStateMirror",
    0x2368: "DungeonAxisMirrorX",
    0x236E: "DungeonAxisMirrorY",
    0x236F: "DungeonAxisChunkY",
    0x2CBB: "MapContextFlag",
    0x2CBD: "ExplorationModeFlag",
    0x2CBE: "BattleModeFlag",
    0x3532: "DungeonXHigh",
    0x3534: "DungeonXLow",
    0x353A: "DungeonYHigh",
    0x353C: "DungeonYLow",
    0x377F: "WalkXFast",
    0x3780: "WalkXSlow",
    0x3782: "WalkYFast",
    0x3783: "WalkYSlow",
    0x379C: "ShipXFast",
    0x379D: "ShipXSlow",
    0x379F: "ShipYFast",
    0x37A0: "ShipYSlow",
    0x28A8: "TownX",
    0x28AA: "TownY",
    0x28A9: "TownVerticalChunk",
    0x28AB: "TownHorizontalChunk",
    0x28C0: "CurrentMap",
    0x2D8F: "PartySlot1",
    0x2D90: "PartySlot2",
    0x2D91: "PartySlot3",
    0x2D92: "PartySlot4",
    0x2D9E: "Gold",
    0x2CF5: "TransportFlag",
    0x0544: "BattleFallbackFlag",
    0x2C32: "ScenarioStart",
    0x353B: "ChunkBorderVHigh",
    0x353D: "ChunkBorderVLow",
    0x3533: "ChunkBorderHHigh",
    0x3535: "ChunkBorderHLow",
    0x356F: "DungeonSpawnXHigh",
    0x3571: "DungeonSpawnYHigh",
    0x2DA1: "InventoryStart",
    0x2E60: "InventoryEnd",
    0x077E: "EventFlagsStart",
    0x079D: "EventFlagsEnd",
    0x2A96: "DungeonFlagStart",
    0x2A9F: "DungeonFlagEnd",
    0x34CF: "CapsuleSlot1",
    0x34D0: "CapsuleSlot2",
    0x34D1: "CapsuleSlot3",
    0x34D2: "CapsuleSlot4",
    0x34D3: "CapsuleSlot5",
    0x34D4: "CapsuleSlot6",
    0x34D5: "CapsuleSlot7",
    0x2EBE: "CharBlock_Maxim",
    0x2F7C: "CharBlock_Selan",
    0x303A: "CharBlock_Guy",
    0x30F8: "CharBlock_Artea",
    0x31B6: "CharBlock_Tia",
    0x3274: "CharBlock_Dekar",
    0x3332: "CharBlock_Lexis",
    0x3940: "EnemySlot_1",
    0x39FE: "EnemySlot_2",
    0x3ABC: "EnemySlot_3",
    0x3B7A: "EnemySlot_4",
    0x3C38: "EnemySlot_5",
    0x3CF6: "EnemySlot_6",
}

NOISE_OFFSETS: set = {
    0x0544, 0x2CB5, 0x2368, 0x236E, 0x236F,
    0x3533, 0x3535, 0x353B, 0x353D,
}

DUNGEON_FLAG_BASE = 0x2A96


def load_dungeon_flags() -> Dict[int, List[str]]:
    flags: Dict[int, List[str]] = {}
    for fname in ["dungeon_flags_snes9x.json", "dungeon_flags_snes9x-nwa.json"]:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", fname)
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                min_addr = min(int(k, 16) for k in data.keys())
                for addr_hex, entries in data.items():
                    addr = int(addr_hex, 16)
                    rel_addr = addr - min_addr + DUNGEON_FLAG_BASE
                    flags[rel_addr] = [e["location"] for e in entries]
                log.info(f"Flags geladen: {fname} -> {len(flags)} Addressen")
            except Exception as e:
                log.warning(f"Konnte {fname} nicht laden: {e}")
    return flags


# ========================================================================
# TCP SERVER (wie memory_reader.py - wartet auf C# Helper)
# ========================================================================
class DiscoveryServer:
    """TCP-Server auf Port 64321. C# Helper verbindet sich aktiv."""

    def __init__(self):
        self.active_conn: Optional[socket.socket] = None
        self.latest_state: dict = {}
        self.latest_dump: Optional[bytes] = None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._running = False

    def start(self) -> bool:
        self._running = True
        t = threading.Thread(target=self._listen, daemon=True)
        t.start()
        return self._ready.wait(timeout=5)

    def _listen(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST, PORT))
            except OSError as e:
                log.error(f"Port {PORT} belegt: {e}")
                self._ready.set()
                return
            s.listen()
            s.settimeout(1.0)
            log.info(f"TCP-Server auf {HOST}:{PORT} - warte auf C# Helper...")
            self._ready.set()
            while self._running:
                conn = None
                try:
                    conn, addr = s.accept()
                    log.info(f"C# Helper verbunden von {addr}")
                    with self._lock:
                        self.active_conn = conn
                    self._handle(conn)
                except socket.timeout:
                    continue
                except Exception as e:
                    if self._running:
                        log.warning(f"Verbindung zu C# Helper verloren: {e}")
                        log.info("Warte auf erneute Verbindung...")
                finally:
                    if conn is not None:
                        with self._lock:
                            if self.active_conn == conn:
                                self.active_conn = None
                        try:
                            conn.close()
                        except:
                            pass

    def _handle(self, conn: socket.socket):
        buf = ""
        try:
            while self._running:
                data = conn.recv(65536)
                if not data:
                    break
                buf += data.decode("utf-8")
                if "\n" in buf:
                    for line in buf.split("\n")[:-1]:
                        if not line.strip():
                            continue
                        try:
                            p = json.loads(line)
                            if not isinstance(p, dict):
                                continue
                            if p.get("type") == "dump":
                                h = p.get("data", "")
                                # Accept legacy 64 KiB helpers so the error is
                                # visible to the caller, but prefer the full
                                # 128 KiB SNES WRAM block (banks 7E and 7F).
                                if len(h) in (0x10000 * 2, WRAM_SIZE * 2):
                                    with self._lock:
                                        self.latest_dump = bytes.fromhex(h)
                                    log.info("WRAM Dump empfangen")
                            elif p.get("type") == "dump_ready":
                                log.info(f"WRAM Datei: {p.get('path')}")
                            else:
                                with self._lock:
                                    self.latest_state.update(p)
                        except json.JSONDecodeError:
                            pass
                    buf = buf.split("\n")[-1]
        except Exception as e:
            log.error(f"Handle: {e}")

    def send(self, cmd: str):
        with self._lock:
            c = self.active_conn
        if c:
            try:
                c.sendall((cmd + "\n").encode("utf-8"))
            except Exception as e:
                log.error(f"Send: {e}")

    def get_dump(self) -> Optional[bytes]:
        with self._lock:
            d = self.latest_dump
            self.latest_dump = None
            return d

    def wait_dump(self, timeout=5) -> Optional[bytes]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            d = self.get_dump()
            if d:
                return d
            time.sleep(0.05)
        return None

    def get_state(self) -> dict:
        with self._lock:
            return dict(self.latest_state)

    def stop(self):
        self._running = False
        with self._lock:
            if self.active_conn:
                try:
                    self.active_conn.close()
                except:
                    pass
            self.active_conn = None


# ========================================================================
# DIFF ANALYZER
# ========================================================================
class WramDiffAnalyzer:
    def __init__(self, dungeon_flags: Dict[int, List[str]]):
        self.dungeon_flags = dungeon_flags
        self.discovered: Dict[str, dict] = {}
        self.history: List[dict] = []

    def compute_diff(self, before: bytes, after: bytes, context: dict = None) -> dict:
        if len(before) != len(after):
            return {"error": f"Laengen mismatch: {len(before)} vs {len(after)}"}
        diffs = []
        for offset in range(len(before)):
            o, n = before[offset], after[offset]
            if o != n:
                diffs.append({
                    "offset": offset, "hex": f"0x{offset:04X}",
                    "old": o, "new": n,
                    "known_label": KNOWN_OFFSETS.get(offset),
                    "noise": offset in NOISE_OFFSETS,
                })
        result = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "context": context or {},
            "total_changes": len(diffs),
            "changes_excluding_noise": len([d for d in diffs if not d["noise"]]),
            "known_changes": len([d for d in diffs if d["known_label"]]),
            "unknown_changes": len([d for d in diffs if not d["known_label"] and not d["noise"]]),
            "diffs_by_category": self._categorize(diffs),
            "diffs": diffs,
            "known_state_before": self._extract_known_state(before),
            "known_state_after": self._extract_known_state(after),
        }
        self.history.append(result)
        return result

    def _extract_known_state(self, wram: bytes) -> dict:
        """Extrahiert ALLE bekannten Addressen aus einem WRAM-Dump als lesbaren State."""
        state = {}
        for offset, label in KNOWN_OFFSETS.items():
            if offset < len(wram):
                val = wram[offset]
                state[label] = val
        # Zusätzliche strukturierte Ausgaben
        if "Gold" in state:
            # Gold ist 3 Byte little-endian
            g_off = 0x2D9E
            if g_off + 2 < len(wram):
                state["Gold_value"] = wram[g_off] | (wram[g_off+1] << 8) | (wram[g_off+2] << 16)
        if "CurrentMap" in state:
            # Map ID ist 2 Byte
            m_off = 0x28C0
            if m_off + 1 < len(wram):
                state["MapID_value"] = wram[m_off] | (wram[m_off+1] << 8)
        # Party-Slots lesbar machen
        party_names = {0: "Maxim", 1: "Selan", 2: "Guy", 3: "Artea", 4: "Tia", 5: "Dekar", 6: "Lexis", 0xFF: "Empty"}
        party = []
        for slot_off in [0x2D8F, 0x2D90, 0x2D91, 0x2D92]:
            if slot_off < len(wram):
                pid = wram[slot_off]
                party.append(party_names.get(pid, f"ID_{pid:02X}"))
        state["Party"] = party
        # DungeonBlocking lesbar
        db = state.get("DungeonBlocking", 255)
        dir_map = {0: "blocked NORTH", 1: "blocked SOUTH", 2: "blocked WEST", 3: "blocked EAST", 255: "clear"}
        state["DungeonBlocking_readable"] = dir_map.get(db, f"unknown_{db}")
        # FacingDirection
        fc = state.get("FacingDirectionStateMirror", 0)
        facing_map = {0x00: "north", 0x01: "south", 0x02: "west", 0x03: "east",
                      0x24: "turn_north", 0x25: "turn_south", 0x26: "turn_west", 0x27: "turn_east"}
        state["FacingDirection_readable"] = facing_map.get(fc, f"0x{fc:02X}")
        # Transport
        tr = state.get("TransportFlag", 0)
        state["Transport_readable"] = "ship" if tr == 0xFF else "walk"
        # Battle
        bf = state.get("BattleModeFlag", 0)
        state["InBattle"] = bf == 0x01
        # MapContext
        mc = state.get("MapContextFlag", 0)
        state["MapContext_readable"] = "dungeon" if mc == 0x11 else "overworld/other"
        return state

    def _categorize(self, diffs: List[dict]) -> dict:
        cats = {"char_stats": [], "enemy_stats": [], "inventory": [],
                "dungeon": [], "flags": [], "unknown": []}
        for d in diffs:
            o = d["offset"]
            if 0x2EBE <= o <= 0x33F1:
                cats["char_stats"].append(d)
            elif 0x3940 <= o <= 0x3DB4:
                cats["enemy_stats"].append(d)
            elif 0x2DA1 <= o <= 0x2E60:
                cats["inventory"].append(d)
            elif (0x2A96 <= o <= 0x2A9F) or (0x3500 <= o <= 0x3600):
                cats["dungeon"].append(d)
            elif (0x077E <= o <= 0x079D) or (0x2C32 <= o <= 0x2C34):
                cats["flags"].append(d)
            elif not d["noise"] and not d["known_label"]:
                cats["unknown"].append(d)
        return {k: v for k, v in cats.items() if v}

    def flag_validation(self, diff_result: dict) -> List[dict]:
        found = []
        for d in diff_result["diffs"]:
            if d["offset"] in self.dungeon_flags:
                found.append({
                    "hex": d["hex"], "old": d["old"], "new": d["new"],
                    "locations": self.dungeon_flags[d["offset"]],
                    "source": "dungeon_flags_snes9x.json",
                })
        return found

    def track_unknowns(self, diff_result: dict):
        for d in diff_result["diffs"]:
            if d["known_label"] or d["noise"]:
                continue
            key = d["hex"]
            if key not in self.discovered:
                self.discovered[key] = {
                    "label": None, "suspected_function": None,
                    "offset": d["offset"], "changes_count": 0,
                    "observed_values": set(),
                    "first_seen": diff_result["timestamp"],
                    "last_seen": diff_result["timestamp"],
                }
            e = self.discovered[key]
            e["changes_count"] += 1
            e["observed_values"].add(d["old"])
            e["observed_values"].add(d["new"])
            e["last_seen"] = diff_result["timestamp"]

    def print_summary(self, diff_result: dict):
        ctx = diff_result.get("context", {})
        action = ctx.get("action", "?")
        print(f"\n{'='*60}")
        print(f"AKTION: {action}")
        if ctx.get("map_name"):
            print(f"Karte: {ctx['map_name']}")
        print(f"Aenderungen: {diff_result['total_changes']} total, "
              f"{diff_result['changes_excluding_noise']} ohne Rauschen, "
              f"{diff_result['known_changes']} bekannt, "
              f"{diff_result['unknown_changes']} unbekannt")

        # STATE VORHER
        sb = diff_result.get("known_state_before", {})
        sa = diff_result.get("known_state_after", {})
        print(f"\n  --- STATE VORHER ---")
        print(f"    MapID: {sb.get('MapID_value', '?')}  |  Party: {sb.get('Party', '?')}")
        print(f"    DungeonPos: ({sb.get('DungeonXHigh', '?')}, {sb.get('DungeonYHigh', '?')})  |  Town: ({sb.get('TownX', '?')}, {sb.get('TownY', '?')})")
        print(f"    Gold: {sb.get('Gold_value', '?')}  |  Transport: {sb.get('Transport_readable', '?')}")
        print(f"    Blocking: {sb.get('DungeonBlocking_readable', '?')}  |  Facing: {sb.get('FacingDirection_readable', '?')}")
        print(f"    Battle: {'JA' if sb.get('InBattle') else 'NEIN'}  |  Context: {sb.get('MapContext_readable', '?')}")

        # STATE NACHHER (nur wenn Unterschiede)
        changed_keys = []
        for k in sb:
            if k in sa and sb[k] != sa[k] and not k.endswith("_readable") and k not in ("Party", "Gold_value", "MapID_value"):
                changed_keys.append(k)
        if changed_keys:
            print(f"\n  --- STATE-AENDERUNGEN ---")
            for k in changed_keys[:10]:
                print(f"    {k}: {sb.get(k)} -> {sa.get(k)}")

        if diff_result.get("diffs_by_category", {}).get("dungeon"):
            print(f"\n  --- Dungeon-Daten ---")
            for d in diff_result["diffs_by_category"]["dungeon"][:10]:
                lbl = d["known_label"] or "?"
                print(f"    {d['hex']}: {d['old']:3d} -> {d['new']:3d}  ({lbl})")
        if diff_result.get("diffs_by_category", {}).get("unknown"):
            print(f"\n  --- UNBEKANNTE Addressen ---")
            for d in diff_result["diffs_by_category"]["unknown"][:15]:
                print(f"    {d['hex']}: {d['old']:3d} -> {d['new']:3d}")
        flag_hits = self.flag_validation(diff_result)
        if flag_hits:
            print(f"\n  --- Validierte Flags ({len(flag_hits)} Treffer) ---")
            for f in flag_hits[:5]:
                locs = ", ".join(f["locations"][:2])
                print(f"    {f['hex']}: {f['old']}->{f['new']} = {locs}")
        print()


def try_press_key(key: str, dur: float = 0.08):
    try:
        import pydirectinput
        pydirectinput.press(key)
        time.sleep(dur)
        return True
    except ImportError:
        return False


def find_helper_exe() -> Optional[str]:
    """Sucht den C# Helper im Projekt."""
    for p in [
        os.path.join(OUTPUT_DIR, "..", "emulator", "csharp_helper", "bin", "Release", "net8.0", "win-x64", "Lufia2AutoTracker.Helper.exe"),
    ]:
        ap = os.path.abspath(p)
        if os.path.exists(ap):
            return ap
    # Config laden
    cfg = os.path.join(OUTPUT_DIR, "..", "runtime_config.json")
    if os.path.exists(cfg):
        try:
            with open(cfg) as f:
                d = json.load(f)
            rp = d.get("helper", {}).get("relative_executable_path", "")
            if rp:
                ap = os.path.abspath(os.path.join(OUTPUT_DIR, "..", rp))
                if os.path.exists(ap):
                    return ap
        except: pass
    return None


def launch_helper() -> Optional[subprocess.Popen]:
    """Startet C# Helper im Hintergrund. Gibt Prozess zurueck."""
    exe = find_helper_exe()
    if not exe:
        print(f"  FEHLER: Lufia2AutoTracker.Helper.exe nicht gefunden!")
        print(f"  Bitte zuerst bauen: dotnet publish emulator\\csharp_helper")
        return None
    print(f"  Starte C# Helper: {os.path.basename(exe)}")
    # CREATE_NO_WINDOW = 0x08000000, damit kein Fenster aufgeht
    proc = subprocess.Popen(
        [exe],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=0x08000000,
        bufsize=0,
    )
    return proc


def launch_helper_and_wait(server: DiscoveryServer, timeout=20) -> bool:
    """Startet C# Helper, wartet auf Verbindung, restartet bei Absturz."""
    proc = launch_helper()
    if not proc:
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        s = server.get_state()
        if s.get("gold") is not None or s.get("map_id") is not None:
            return True
        # Pruefen ob Prozess noch lebt
        if proc.poll() is not None:
            log.warning(f"C# Helper gestorben (exit {proc.returncode}). Neustart...")
            # stdout/stderr auslesen
            out, err = proc.communicate(timeout=1)
            if out:
                log.info(f"Helper stdout: {out[-500:].decode('utf-8', errors='replace')}")
            if err:
                log.info(f"Helper stderr: {err[-500:].decode('utf-8', errors='replace')}")
            proc = launch_helper()
            if not proc:
                return False
            deadline = time.time() + timeout  # Reset deadline nach Neustart
        time.sleep(1)
    print(f"  Keine Verbindung nach {timeout}s.")
    if proc and proc.poll() is None:
        proc.terminate()
    return False


def keep_helper_alive(server: DiscoveryServer):
    """Hintergrund-Thread: ueberwacht C# Helper, restartet bei Bedarf."""
    def _watch():
        while server._running:
            with server._lock:
                conn_dead = server.active_conn is None
            if conn_dead:
                log.info("Keine aktive Verbindung. Starte C# Helper neu...")
                launch_helper()
            time.sleep(5)
    t = threading.Thread(target=_watch, daemon=True)
    t.start()


# ========================================================================
# MAIN
# ========================================================================
def main():
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    print()
    print("=" * 60)
    print("  WRAM DISCOVERY AGENT v1.2")
    print("  Automatische WRAM-Adress-Ermittlung")
    print("=" * 60)
    print()
    print("  STARTE TCP-SERVER auf Port 64321...")
    print()

    server = DiscoveryServer()
    if not server.start():
        print("  FEHLER: Port 64321 belegt.")
        print("  start_agent.ps1 beenden (Ctrl+C) und erneut versuchen.")
        sys.exit(1)

    print("  Starte C# Helper (unsichtbar)...")
    if not launch_helper_and_wait(server, timeout=20):
        server.stop()
        sys.exit(1)

    # Auto-Restart im Hintergrund
    keep_helper_alive(server)

    dungeon_flags = load_dungeon_flags()
    analyzer = WramDiffAnalyzer(dungeon_flags)

    state = server.get_state()
    print(f"\n  C# Helper verbunden (kein separates Fenster)!")
    print(f"  Map ID: {state.get('map_id', '?')}")
    print(f"  Position: ({state.get('dungeon_x', '?')}, {state.get('dungeon_y', '?')})")
    print(f"  Gold: {state.get('gold', '?')}")
    print()

    # Ersten Dump holen
    server.send("DUMP")
    dump_before = server.wait_dump(timeout=8)
    if not dump_before:
        print("  FEHLER: Kein WRAM-Dump vom C# Helper")
        server.stop()
        sys.exit(1)
    print(f"  WRAM Dump: {len(dump_before)} Bytes")
    print()

    print("  MODI:")
    print("  1 - MANUAL: ENTER=Snapshot, Aktion, ENTER=Diff")
    print("  2 - MONITOR: Ueberwacht WRAM-Aenderungen live")
    print("  3 - AUTO: Fuehrt Tastendruecke automatisch aus")
    print("  4 - AUTO_DUNGEON: Dungeon-Aktionen (Tuer, Hebel)")
    print()
    mode = input("  Modus (1/2/3/4): ").strip()
    print()

    try:
        if mode == "1":
            run_manual(server, analyzer)
        elif mode == "2":
            run_monitor(server, analyzer)
        elif mode == "3":
            run_auto(server, analyzer)
        elif mode == "4":
            run_auto_dungeon(server, analyzer)
        else:
            print(f"  Ungueltig: {mode}")
    except KeyboardInterrupt:
        print("\n  Abbruch.")
    finally:
        server.stop()
        save_results(analyzer, dungeon_flags)
        print(f"\n  Ergebnisse in: {OUTPUT_DIR}")
        print("  - discovered_addresses.json")
        print("  - validated_addresses.json")


# ========================================================================
# MODI
# ========================================================================
def run_manual(server: DiscoveryServer, analyzer: WramDiffAnalyzer):
    print("  MANUAL MODE (ENTER=Snapshot, Aktion, ENTER=Diff, q=Ende)\n")
    n = 0
    while True:
        input("  Vorher? (ENTER) ")
        server.send("DUMP")
        dump_before = server.wait_dump(timeout=5)
        if not dump_before:
            continue
        print("  Vorher gesichert. Aktion ausfuehren...")
        input("  Nachher? (ENTER) ")
        server.send("DUMP")
        dump_after = server.wait_dump(timeout=5)
        if not dump_after:
            continue
        aname = input("  Name (z.B. 'open_door'): ").strip() or f"snap_{n}"
        state = server.get_state()
        ctx = {"action": aname, "map_id": state.get("map_id"),
               "map_name": state.get("map_name")}
        diff = analyzer.compute_diff(dump_before, dump_after, ctx)
        analyzer.track_unknowns(diff)
        analyzer.print_summary(diff)
        save_snapshot(dump_before, dump_after, aname, diff)
        n += 1


def run_monitor(server: DiscoveryServer, analyzer: WramDiffAnalyzer):
    print("  MONITOR MODE (CTRL+C Ende)\n")
    server.send("DUMP")
    prev = server.wait_dump(timeout=5)
    if not prev:
        return
    while True:
        time.sleep(1.0)
        server.send("DUMP")
        curr = server.wait_dump(timeout=5)
        if not curr:
            continue
        state = server.get_state()
        ctx = {"action": "monitor", "map_id": state.get("map_id"),
               "map_name": state.get("map_name")}
        diff = analyzer.compute_diff(prev, curr, ctx)
        analyzer.track_unknowns(diff)
        if diff["total_changes"] > 0:
            analyzer.print_summary(diff)
        prev = curr


def run_auto(server: DiscoveryServer, analyzer: WramDiffAnalyzer):
    print("  AUTO MODE\n")
    server.send("DUMP")
    dump_before = server.wait_dump(timeout=5)
    if not dump_before:
        print("  Kein initialer Dump. Abbruch.")
        return
    actions = [
        ("move_north", [("up", 0.1)]),
        ("move_south", [("down", 0.1)]),
        ("move_east", [("right", 0.1)]),
        ("move_west", [("left", 0.1)]),
        ("press_a", [("a", 0.1)]),
        ("press_b", [("b", 0.1)]),
        ("press_x_menu", [("x", 0.3)]),
        ("press_x_close", [("x", 0.3)]),
        ("press_y_tool", [("y", 0.1)]),
        ("press_select", [("space", 0.1)]),
    ]
    for aname, keys in actions:
        state = server.get_state()
        ctx = {"action": aname, "map_id": state.get("map_id"),
               "map_name": state.get("map_name")}
        for k, d in keys:
            try_press_key(k, d)
        time.sleep(0.5)
        server.send("DUMP")
        dump_after = server.wait_dump(timeout=5)
        if not dump_after:
            continue
        diff = analyzer.compute_diff(dump_before, dump_after, ctx)
        analyzer.track_unknowns(diff)
        analyzer.print_summary(diff)
        dump_before = dump_after
        time.sleep(1.0)


def run_auto_dungeon(server: DiscoveryServer, analyzer: WramDiffAnalyzer):
    print("  AUTO DUNGEON MODE\n")
    actions = [
        ("walk_into_door", [("up", 0.3), ("a", 0.1)]),
        ("try_interact", [("a", 0.5)]),
        ("press_b_cancel", [("b", 0.2)]),
        ("open_menu", [("x", 0.3)]),
        ("close_menu", [("x", 0.3)]),
    ]
    for aname, keys in actions:
        state = server.get_state()
        ctx = {"action": aname, "map_id": state.get("map_id"),
               "map_name": state.get("map_name")}
        server.send("DUMP")
        dump_before = server.wait_dump(timeout=5)
        if not dump_before:
            continue
        for k, d in keys:
            try_press_key(k, d)
        time.sleep(0.8)
        server.send("DUMP")
        dump_after = server.wait_dump(timeout=5)
        if not dump_after:
            continue
        diff = analyzer.compute_diff(dump_before, dump_after, ctx)
        analyzer.track_unknowns(diff)
        analyzer.print_summary(diff)
        save_snapshot(dump_before, dump_after, aname, diff)
        time.sleep(1.0)


# ========================================================================
# SPEICHERN
# ========================================================================
def save_snapshot(before: bytes, after: bytes, action_name: str, diff: dict):
    ts = time.strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r'[^a-zA-Z0-9_]', '_', action_name)
    path = os.path.join(SNAPSHOT_DIR, f"{ts}_{safe}.json")
    changed = {}
    for d in diff["diffs"]:
        changed[d["hex"]] = {"old": d["old"], "new": d["new"], "label": d["known_label"]}
    snap = {
        "action": action_name, "timestamp": diff["timestamp"],
        "context": diff["context"],
        "summary": {"total": diff["total_changes"], "unknown": diff["unknown_changes"]},
        "changed_offsets": changed,
        "known_state_before": diff.get("known_state_before", {}),
        "known_state_after": diff.get("known_state_after", {}),
    }
    with open(path, "w") as f:
        json.dump(snap, f, indent=2)
    log.info(f"Snapshot: {path}")


def save_results(analyzer: WramDiffAnalyzer, dungeon_flags: dict):
    # discovered
    dp = os.path.join(OUTPUT_DIR, "discovered_addresses.json")
    dl = []
    for key, data in analyzer.discovered.items():
        dl.append({
            "hex": key, "offset": data["offset"],
            "changes_count": data["changes_count"],
            "observed_values": sorted(data["observed_values"]),
            "first_seen": data["first_seen"], "last_seen": data["last_seen"],
            "possible_flags": dungeon_flags.get(data["offset"], []),
        })
    dl.sort(key=lambda x: x["offset"])
    with open(dp, "w") as f:
        json.dump({
            "generated_by": "WRAM Discovery Agent v1.1",
            "wram_base": f"0x{WRAM_BASE_KNOWN:06X}",
            "total_discovered": len(dl),
            "addresses": dl,
        }, f, indent=2)
    log.info(f"{dp} ({len(dl)} Addressen)")

    # validated
    vp = os.path.join(OUTPUT_DIR, "validated_addresses.json")
    ve = []
    for h in analyzer.history:
        fh = analyzer.flag_validation(h)
        if fh:
            ve.append({"timestamp": h["timestamp"], "context": h["context"], "flag_hits": fh})
    with open(vp, "w") as f:
        json.dump({
            "generated_by": "WRAM Discovery Agent v1.1",
            "total_validations": len(ve),
            "entries": ve,
        }, f, indent=2)
    log.info(f"{vp} ({len(ve)} Validierungen)")


if __name__ == "__main__":
    main()
