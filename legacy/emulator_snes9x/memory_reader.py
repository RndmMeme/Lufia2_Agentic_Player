import socket
import json
import logging
import threading
from typing import Dict, Any
import numpy as np
import time
import os
from emulator.item_db import ITEM_DB
from emulator.map_db import MAP_DB
from emulator.boss_db import BOSS_DB
from emulator.zone_db import zone_for_map

# Load static data once
SHOP_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "shop_addresses.json")
try:
    with open(SHOP_DATA_PATH, "r") as f:
        SHOP_ADDRESSES = json.load(f)["shops"]
except Exception as e:
    logging.warning(f"Could not load shop_addresses.json: {e}")
    SHOP_ADDRESSES = []

SPELL_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "items_spells.json")
try:
    with open(SPELL_DATA_PATH, "r") as f:
        SPELL_DB = json.load(f)
except Exception as e:
    logging.warning(f"Could not load items_spells.json: {e}")
    SPELL_DB = {}

SPELLS_INFO_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "spells_info.json")
try:
    with open(SPELLS_INFO_PATH, "r") as f:
        SPELLS_INFO = json.load(f)
except Exception as e:
    logging.warning(f"Could not load spells_info.json: {e}")
    SPELLS_INFO = {}

COMBAT_ITEMS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "combat_items.json")
try:
    with open(COMBAT_ITEMS_PATH, "r") as f:
        COMBAT_ITEMS = json.load(f)
except Exception as e:
    logging.warning(f"Could not load combat_items.json: {e}")
    COMBAT_ITEMS = {}

MONSTER_TABLE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "monster_overworld_sprites.txt"
)
MONSTER_DB = {}
try:
    with open(MONSTER_TABLE_PATH, "r", encoding="utf-8") as monster_file:
        for line in monster_file:
            parts = line.strip().split(maxsplit=2)
            if len(parts) != 3:
                continue
            monster_id = int(parts[0], 16)
            MONSTER_DB[monster_id] = {
                "id": monster_id,
                "overworld_sprite_id": int(parts[1], 16),
                "name": parts[2],
            }
except Exception as e:
    logging.warning(f"Could not load monster_overworld_sprites.txt: {e}")

def _categorize_spell(spell_meta):
    name = str(spell_meta.get("name", "")).lower()
    desc = str(spell_meta.get("description", "")).lower()
    text = f"{name} {desc}"

    healing_keywords = [
        "restores", "restore", "cures", "cure", "revives", "revive",
        "wakes up", "wakes", "refill allies", "all hp", "allies",
    ]
    buff_keywords = [
        "increases", "increase", "repels", "repel", "during battle",
        "mgr", "dfp", "atp", "agl",
    ]
    debuff_keywords = [
        "decreases", "decrease", "inflicts", "sleep", "confusion",
        "instant death", "freezes magic", "puts foes",
    ]
    offensive_keywords = [
        "attack", "damage", "magic attack", "foes by 1/",
    ]

    if any(keyword in text for keyword in healing_keywords):
        return "Healing"
    if any(keyword in text for keyword in buff_keywords):
        return "Buff"
    if any(keyword in text for keyword in debuff_keywords):
        return "Debuff"
    if any(keyword in text for keyword in offensive_keywords):
        return "Offensive"
    return "Offensive"

def _preferred_spell_group(category):
    if category in ("Healing", "Buff"):
        return "PARTY"
    return "ENEMY"


FACING_CONTACT_LABELS = {
    0x00: "dir_north",
    0x01: "dir_south",
    0x02: "dir_west",
    0x03: "dir_east",
    0x24: "turn_north",
    0x25: "turn_south",
    0x26: "turn_west",
    0x27: "turn_east",
    0x28: "turn_south_to_north",
    0x29: "turn_north_to_south",
    0x2A: "turn_east_to_west",
    0x2B: "turn_west_to_east",
}


def _decode_dungeon_blocking(value):
    labels = {
        0: "blocked_north",
        1: "blocked_south",
        2: "blocked_west",
        3: "blocked_east",
        255: "clear",
    }
    return labels.get(value, f"unknown_{value}")


def _decode_facing_contact(value):
    label = FACING_CONTACT_LABELS.get(value, f"unknown_0x{value:02X}")
    facing_direction = None

    if value == 0x00:
        facing_direction = "north"
    elif value == 0x01:
        facing_direction = "south"
    elif value == 0x02:
        facing_direction = "west"
    elif value == 0x03:
        facing_direction = "east"
    elif value in (0x24, 0x28, 0x29):
        facing_direction = "north" if value in (0x24, 0x28) else "south"
    elif value in (0x25,):
        facing_direction = "south"
    elif value in (0x26, 0x2A):
        facing_direction = "west"
    elif value in (0x27, 0x2B):
        facing_direction = "east"

    return {
        "facing_contact_label": label,
        "facing_direction": facing_direction,
    }


def _decode_map_context(value):
    if value == 0x11:
        return "map"
    if value == 0x00:
        return "overworld_or_nonmap"
    return f"unknown_0x{value:02X}"


def _decode_runtime_mode(exploration_value, battle_value):
    if battle_value == 0x01:
        return "battle_or_results"
    if exploration_value == 0x01:
        return "exploration"
    if exploration_value == 0x04:
        return "tool_menu_opening"
    return "other"


def _decode_battle_target_mask(value):
    """Decode the confirmed command target byte, not the temporary cursor."""
    raw = int(value or 0) & 0xFF
    is_enemy = bool(raw & 0x80)
    bit_mask = raw & (0x3F if is_enemy else 0x1F)
    limit = 6 if is_enemy else 5
    return {
        "raw": raw,
        "side": "enemy" if is_enemy else "party",
        "bit_mask": bit_mask,
        "indices": [index for index in range(limit) if bit_mask & (1 << index)],
        "target_labels": [
            (
                f"enemy_{index}"
                if is_enemy
                else ("capsule" if index == 4 else ("Guy", "Arty", "Selan", "Tia")[index])
            )
            for index in range(limit)
            if bit_mask & (1 << index)
        ],
        "is_multi_target": bit_mask != 0 and (bit_mask & (bit_mask - 1)) != 0,
    }


def _decode_combat_status(value):
    raw = int(value or 0) & 0xFF
    bits = (
        (0x01, "poison"),
        (0x02, "silence"),
        (0x04, "disabled"),
        (0x08, "paralyze"),
        (0x10, "confusion"),
        (0x20, "sleep"),
    )
    return [name for bit, name in bits if raw & bit]


class MemoryReader:
    def __init__(self, host="127.0.0.1", port=64321):
        """
        Acts as a local TCP Server to receive continuous JSON state updates 
        from the Lufia 2 C# Tracker Helper.
        """
        self.host = host
        self.port = port
        self.latest_state = None
        self.latest_dump = None
        self.latest_dump_path = None
        self.active_conn = None
        self.packet_count = 0
        self.last_packet_at = None
        self._lock = threading.Lock()
        
        # Start background listener
        self.server_thread = threading.Thread(target=self._listen_for_state, daemon=True)
        self.server_thread.start()

    def send_command(self, cmd: str):
        """Sends a command string to the connected C# helper."""
        with self._lock:
            conn = self.active_conn
        
        if conn:
            try:
                # Always terminate commands with a newline for the C# listener
                payload = cmd if cmd.endswith("\n") else cmd + "\n"
                conn.sendall(payload.encode('utf-8'))
                logging.info(f"Sent command to C#: {cmd.strip()}")
            except Exception as e:
                logging.error(f"Failed to send command: {e}")
        else:
            logging.warning("No active C# connection to send command to.")

    def get_latest_dump(self):
        """Retrieves and clears the most recent WRAM dump."""
        with self._lock:
            d = self.latest_dump
            self.latest_dump = None
            return d

    def get_latest_dump_path(self):
        """Retrieves and clears the most recent WRAM dump file path."""
        with self._lock:
            p = self.latest_dump_path
            self.latest_dump_path = None
            return p

    def _listen_for_state(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                # Allow the socket to be reused immediately after closure (fixes 'Address already in use')
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((self.host, self.port))
            except OSError as e:
                if e.errno == 10048:
                    msg = f"\nCRITICAL ERROR: Port {self.port} is already in use.\n" \
                          f"Is another instance of the agent ('main.py' or 'battle_finder.py') already running?\n" \
                          f"Please close other Python windows or scripts and try again."
                    logging.error(msg)
                    print(msg)
                else:
                    logging.error(f"Socket Bind Error: {e}")
                return

            s.listen()
            logging.info(f"MemoryReader listening on {self.host}:{self.port}")
            
            while True:
                conn, addr = s.accept()
                logging.info(f"MemoryReader: Accepted connection from {addr}")
                with self._lock:
                    self.active_conn = conn
                with conn:
                    # In a real continuous stream, we'd read loop this connection
                    buffer = ""
                    try:
                        while True:
                            # Increase receive buffer for large dumps
                            data = conn.recv(65536)
                            if not data:
                                break
                            
                            buffer += data.decode('utf-8')
                            
                            # Parse complete JSON lines Delimited by \n from TrackerClient.cs
                            if '\n' in buffer:
                                lines = buffer.split('\n')
                                for line in lines[:-1]: # All complete lines
                                    if line.strip():
                                        try:
                                            parsed = json.loads(line)
                                            # Intercept special payload types
                                            if parsed.get("type") == "dump":
                                                with self._lock:
                                                    self.latest_dump = parsed.get("data")
                                                    self.packet_count += 1
                                                    self.last_packet_at = time.time()
                                                logging.info("Received WRAM Dump from C#.")
                                            elif parsed.get("type") == "dump_ready":
                                                with self._lock:
                                                    self.latest_dump_path = parsed.get("path")
                                                    self.packet_count += 1
                                                    self.last_packet_at = time.time()
                                                logging.info(f"Binary WRAM Dump ready at: {self.latest_dump_path}")
                                            else:
                                                with self._lock:
                                                    if self.latest_state is None:
                                                        self.latest_state = parsed
                                                    else:
                                                        # Merge minimal updates into the full cached state
                                                        self.latest_state.update(parsed)
                                                    self.packet_count += 1
                                                    self.last_packet_at = time.time()
                                        except json.JSONDecodeError:
                                            pass
                                
                                buffer = lines[-1] # Keep the incomplete remainder
                    except Exception as e:
                        logging.error(f"TCP Stream Error: {e}")
                    finally:
                        with self._lock:
                            if self.active_conn == conn:
                                self.active_conn = None

    def get_game_state(self) -> Dict[str, Any]:
        """
        Fetches the most recently cached game state from the C# helper.
        """
        with self._lock:
            state = self.latest_state
            active_conn = self.active_conn is not None
            packet_count = self.packet_count
            last_packet_at = self.last_packet_at

        if not state:
            return {
                "x": 0, "y": 0, "gold": 0, "map_id": 0,
                "previous_map_id": 0, "current_map": 0,
                "party": [], "characters": {}, "enemies": [], "in_battle": False,
                "dungeon_blocking": 255,
                "dungeon_blocking_label": "clear",
                "map_context_flag": 0,
                "map_context_label": "overworld_or_nonmap",
                "exploration_mode_flag": 0,
                "battle_mode_flag": 0,
                "runtime_mode_label": "other",
                "facing_contact_state": 0,
                "facing_contact_label": "dir_north",
                "facing_direction": "north",
                "dungeon_axis_mirror_x": 0,
                "dungeon_axis_mirror_y": 0,
                "dungeon_axis_chunk_y": 0,
                "blocked_ahead": False,
                "blocked_direction": None,
                "_reader_ready": False,
                "_reader_connected": active_conn,
                "_reader_packet_count": packet_count,
                "_reader_last_packet_at": last_packet_at
            }
            
        stats = state.get("party_stats", [])
        active_ids = state.get("characters", [])
        if not isinstance(active_ids, list):
            active_ids = []

        char_names = ["Maxim", "Selan", "Guy", "Artea", "Tia", "Dekar", "Lexis"]
        party = []
        for cid in active_ids:
            if isinstance(cid, str) and cid.strip():
                party.append(cid.strip())
            elif isinstance(cid, int) and 0 <= cid < len(char_names):
                party.append(char_names[cid])
            else:
                party.append("Unknown")
        
        characters = {}
        for i, name in enumerate(party):
            if i < len(stats):
                s = stats[i]
                # Resolve learned combat spells in actual spellbook order.
                raw_spells = s.get("spells", [])
                resolved_spells = []
                for spell_idx, sp_id in enumerate(raw_spells):
                    spell_hex = f"{int(sp_id):02X}"
                    spell_meta = SPELLS_INFO.get(spell_hex)
                    if not spell_meta or not spell_meta.get("combat", False):
                        continue
                    true_slot = spell_idx + 1
                    category = _categorize_spell(spell_meta)
                    resolved_spells.append({
                        "name": spell_meta.get("name", f"Spell_{spell_hex}"),
                        "id": sp_id,
                        "cost": spell_meta.get("mp", 0),
                        "abs_idx": spell_idx,
                        "slot": true_slot,
                        "menu_row": (true_slot - 1) // 2,
                        "is_right_column": (true_slot % 2 == 0),
                        "category": category,
                        "preferred_group": _preferred_spell_group(category),
                        "desc": spell_meta.get("description", ""),
                    })

                ip_value = int(s.get("ip", 0) or 0)
                ip_attacks = s.get("ip_attacks", []) or []
                
                characters[name] = {
                    "hp": s.get("hp", 0),
                    "max_hp": s.get("max_hp", 0),
                    "mp": s.get("mp", 0),
                    "max_mp": s.get("max_mp", 0),
                    "level": s.get("level", 0),
                    "status": s.get("status", 0),
                    "status_effects": _decode_combat_status(s.get("status", 0)),
                    "ip": ip_value,
                    "spells": resolved_spells,
                    "ip_attacks": ip_attacks,
                }
        
        enemy_hps = state.get("enemy_hp_list", [])
        enemy_stats = state.get("enemy_stats", []) or []
        enemy_names = state.get("enemy_names", [f"Enemy {j+1}" for j in range(len(enemy_hps))])
        enemies = []
        for j, ehp in enumerate(enemy_hps):
            if not isinstance(ehp, int) or ehp <= 0:
                continue
            stat = enemy_stats[j] if j < len(enemy_stats) else {}
            monster_id = int(stat.get("id", 0) or 0)
            monster_meta = MONSTER_DB.get(monster_id, {})
            live_name = (
                stat.get("name")
                or (enemy_names[j] if j < len(enemy_names) else f"Enemy {j+1}")
            )
            enemy = {
                "slot": j,
                "id": monster_id,
                "id_hex": f"{monster_id:02X}",
                "name": live_name,
                "table_name": monster_meta.get("name"),
                "overworld_sprite_id": monster_meta.get("overworld_sprite_id"),
                "identity_matches_table": (
                    not monster_meta
                    or " ".join(str(live_name).split()).casefold()
                    == " ".join(str(monster_meta.get("name", "")).split()).casefold()
                ),
                "hp": ehp,
                "max_hp": int(stat.get("max_hp", 0) or 0),
                "mp": int(stat.get("mp", 0) or 0),
                "max_mp": int(stat.get("max_mp", 0) or 0),
                "level": int(stat.get("level", 0) or 0),
                "status": int(stat.get("status", 0) or 0),
                "status_effects": _decode_combat_status(stat.get("status", 0)),
                "attack": int(stat.get("attack", 0) or 0),
                "defense": int(stat.get("defense", 0) or 0),
                "strength": int(stat.get("strength", 0) or 0),
                "agility": int(stat.get("agility", 0) or 0),
                "intelligence": int(stat.get("intelligence", 0) or 0),
                "guts": int(stat.get("guts", 0) or 0),
                "magic_resistance": int(stat.get("magic_resistance", 0) or 0),
                "pos": "Front"
            }
            enemies.append(enemy)

        map_id_val = state.get("map_id", 0)
        map_hex = f"{map_id_val:02X}"
        map_name = MAP_DB.get(map_hex, f"Unknown Map ({map_hex})")
        zone = zone_for_map(map_id_val)
        previous_map_id = int(state.get("previous_map_id", 0) or 0)
        previous_map_hex = f"{previous_map_id:02X}"
        previous_zone = zone_for_map(previous_map_id)

        parsed_inventory = self._parse_inv(state)
        dungeon_blocking = state.get("dungeon_blocking", 255)
        map_context_flag = int(state.get("map_context_flag", 0) or 0)
        exploration_mode_flag = int(state.get("exploration_mode_flag", 0) or 0)
        battle_mode_flag = int(state.get("battle_mode_flag", 0) or 0)
        battle_party_commands = []
        for raw_command in state.get("battle_party_commands", []) or []:
            target = _decode_battle_target_mask(raw_command.get("target_mask", 0))
            battle_party_commands.append({
                "slot": int(raw_command.get("slot", 0) or 0),
                "target_mask": target["raw"],
                "target_side": target["side"],
                "target_bits": target["bit_mask"],
                "target_indices": target["indices"],
                "target_labels": target["target_labels"],
                "is_multi_target": target["is_multi_target"],
                "command": int(raw_command.get("command", 0) or 0),
                "selected_action": int(raw_command.get("selected_action", 0) or 0),
                "actor_mask": int(raw_command.get("actor_mask", 0) or 0),
            })
        facing_contact_state = state.get("facing_contact_state", 0)
        facing_contact = _decode_facing_contact(int(facing_contact_state or 0))
        blocking_value = int(dungeon_blocking if dungeon_blocking is not None else 255)
        blocked_ahead = blocking_value in (0, 1, 2, 3)
        blocked_direction_map = {
            0: "north",
            1: "south",
            2: "west",
            3: "east",
        }

        return {
            "x": state.get("player_x", 0), "y": state.get("player_y", 0),
            "dungeon_x": state.get("dungeon_x", 0), "dungeon_y": state.get("dungeon_y", 0),
            "dungeon_blocking": dungeon_blocking,
            "dungeon_blocking_label": _decode_dungeon_blocking(blocking_value),
            "map_context_flag": map_context_flag,
            "map_context_label": _decode_map_context(map_context_flag),
            "exploration_mode_flag": exploration_mode_flag,
            "battle_mode_flag": battle_mode_flag,
            "battle_active_target_index": int(
                state.get("battle_active_target_index", 0) or 0
            ),
            "battle_party_commands": battle_party_commands,
            "runtime_mode_label": _decode_runtime_mode(exploration_mode_flag, battle_mode_flag),
            "facing_contact_state": facing_contact_state,
            "facing_contact_label": facing_contact["facing_contact_label"],
            "facing_direction": facing_contact["facing_direction"],
            "dungeon_axis_mirror_x": state.get("dungeon_axis_mirror_x", 0),
            "dungeon_axis_mirror_y": state.get("dungeon_axis_mirror_y", 0),
            "dungeon_axis_chunk_y": state.get("dungeon_axis_chunk_y", 0),
            "blocked_ahead": blocked_ahead,
            "blocked_direction": blocked_direction_map.get(blocking_value),
            "map_id": map_id_val,
            "map_name": map_name,
            "previous_map_id": previous_map_id,
            "previous_map_name": MAP_DB.get(
                previous_map_hex,
                f"Unknown Map ({previous_map_hex})",
            ),
            "previous_zone_id": previous_zone["id"] if previous_zone else None,
            "previous_zone_name": previous_zone["name"] if previous_zone else None,
            "zone_id": zone["id"] if zone else None,
            "zone_id_hex": zone["id_hex"] if zone else None,
            "zone_name": zone["name"] if zone else None,
            "party": party,
            "characters": characters,
            "char_stats": characters,
            "party_stats": stats,
            "enemies": enemies,
            "hp": [s.get('hp', 0) for s in stats],
            "max_hp": [s.get('max_hp', 1) for s in stats],
            "mp": [s.get('mp', 0) for s in stats],
            "status": [s.get('status', 0) for s in stats],
            "inventory": parsed_inventory,
            "combat_inventory": self._derive_combat_inventory(parsed_inventory),
            "gold": state.get("gold", 0),
            "in_battle": state.get("in_battle", False),
            "is_game_over": all(s.get('hp', 0) == 0 for s in stats) if stats else False,
            "transport": state.get("transport_mode", "walk"),
            "loc_type": "Dungeon",
            "_reader_ready": True,
            "_reader_connected": active_conn,
            "_reader_packet_count": packet_count,
            "_reader_last_packet_at": last_packet_at
        }

    def _parse_inv(self, state):
        raw_inv = state.get("raw_inventory", [])
        parsed_inv = []
        for slot in raw_inv:
            b1_id, b2_qty = slot.get("byte1"), slot.get("byte2")
            if not b2_qty: continue
            is_odd = b2_qty % 2 != 0
            qty = (b2_qty - 1) // 2 if is_odd else b2_qty // 2
            parity = "Odd" if is_odd else "Even"
            item_hex = f"{b1_id:02X}_{parity}"
            raw_slot_index = int(slot.get("slot", len(parsed_inv)))
            parsed_inv.append({
                "name": ITEM_DB.get(item_hex, f"Unknown Item"),
                "qty": qty,
                "abs_idx": raw_slot_index,
                "slot": raw_slot_index + 1,
                "occupied_ordinal": len(parsed_inv) + 1,
                "item_id": f"{b1_id:02X}",
                "list_type": parity.lower(),
            })
        return parsed_inv

    def _derive_combat_inventory(self, parsed_inv):
        combat_items = []
        for item in parsed_inv:
            item_id = item.get("item_id")
            list_type = item.get("list_type")
            if not item_id or not list_type:
                continue
            meta = COMBAT_ITEMS.get(list_type, {}).get(item_id)
            if not meta:
                continue
            combat_items.append({
                "name": item.get("name", meta.get("name", "Unknown Item")),
                "qty": item.get("qty", 0),
                "abs_idx": item.get("abs_idx", 0),
                "slot": item.get("slot", 1),
                "occupied_ordinal": item.get("occupied_ordinal"),
                "menu_index": max(0, int(item.get("abs_idx", 0))),
                "desc": meta.get("desc", ""),
                "target": meta.get("target", "Single"),
            })
        return combat_items


    def _read_shop_raw(self, rom_offset: int, length: int) -> bytes:
        """Helper to call C# ReadShopRaw."""
        # This requires sending a synchronous command or waiting for response.
        # Since MemoryReader is passive, we can't easily do this in get_game_state.
        # However, the C# helper could populate state.Shops automatically if we configure it.
        # For now, let's use the state.Shops if C# populated it.
        return b""

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    reader = MemoryReader()
    print("Memory Reader Initialized. Awaiting C# Helper connection.")
    # Block script to keep alive for testing
    import time
    try:
        while True:
            time.sleep(1)
            print("Latest state:", reader.get_game_state())
    except KeyboardInterrupt:
        print("Exiting.")
