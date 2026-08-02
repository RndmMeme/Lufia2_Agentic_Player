import ctypes
import psutil
import json
import re
import os
import math

# Snes9x 1.62.3 Base Offsets
BASE_OFFSET = 0x140000000
GOLD_ADDR = 0xA32D9E
PARTY_SLOTS = 0xA32D8F
CHAR_STATS_BASE = 0xA32EBE
INV_START = 0xA32DA1
INV_END = 0xA32E60
SCENARIO_START = 0xA32C32
MAP_ID_ADDR = 0xA328C0

# Coordinates & Transport
TRANSPORT_FLAG = 0xA32CF5 # 0x00=Walk, 0xFF=Ship/Airship
SHIP_X_FAST = 0xA3379C
SHIP_X_SLOW = 0xA3379D
SHIP_Y_FAST = 0xA3379F
SHIP_Y_SLOW = 0xA337A0
WALK_X_FAST = 0xA3377F
WALK_X_SLOW = 0xA33780
WALK_Y_FAST = 0xA33782
WALK_Y_SLOW = 0xA33783

DUNGEON_X_HIGH = 0xA33532
DUNGEON_Y_HIGH = 0xA3353A
TOWN_X = 0xA328A8
TOWN_Y = 0xA328AA

DUNGEON_FLAGS_BASE = 0xA32A96
CAPSULE_SLOTS = 0xA334CF  # 7 slots

def get_process():
    for p in psutil.process_iter():
        if 'snes9x' in p.name().lower():
            return p
    return None

def read_mem(handle, addr, size):
    buf = ctypes.create_string_buffer(size)
    bytes_read = ctypes.c_size_t()
    if ctypes.windll.kernel32.ReadProcessMemory(handle, ctypes.c_uint64(addr), buf, size, ctypes.byref(bytes_read)):
        return list(buf.raw)
    return None

def load_json_data(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def get_maiden_count(handle, spoiler_data, dungeon_flags_map):
    if not spoiler_data or not dungeon_flags_map:
        return 0
    
    maiden_locations = {}
    for entry in spoiler_data:
        loc = entry.get('location')
        item = entry.get('item', '')
        if any(m in item for m in ["Claire", "Lisa", "Marie"]):
            maiden_locations[loc] = item

    found_maidens = set()
    for addr_str, locations in dungeon_flags_map.items():
        addr = int(addr_str, 16)
        val = read_mem(handle, BASE_OFFSET + addr, 1)[0]
        for loc_info in locations:
            loc_name = loc_info.get('location')
            flag = int(loc_info.get('flag', '00'), 16)
            if (val & flag) and loc_name in maiden_locations:
                found_maidens.add(maiden_locations[loc_name])
                
    return len(found_maidens)

def get_capsule_monsters(handle):
    names = ["Jelze", "Flash", "Gusto", "Zeppy", "Darbi", "Sully", "Blaze"]
    active_capsules = []
    slots = read_mem(handle, BASE_OFFSET + CAPSULE_SLOTS, 7)
    for i, val in enumerate(slots):
        if val != 0:
            active_capsules.append(names[i])
    return active_capsules

def get_nearby_locations(x, y, locations):
    nearby = []
    MAP_SIZE = 4000
    HALF_MAP = MAP_SIZE // 2
    
    for loc_name, coords in locations.items():
        # Shortest distance with wrap-around
        dx = (coords[0] - x + HALF_MAP) % MAP_SIZE - HALF_MAP
        dy = (coords[1] - y + HALF_MAP) % MAP_SIZE - HALF_MAP
        
        dist = math.sqrt(dx**2 + dy**2)
        
        if dist < 400:
            # Calculate direction (0 deg = East, 90 deg = South)
            angle = math.degrees(math.atan2(dy, dx))
            if -22.5 <= angle < 22.5: dir_str = "East"
            elif 22.5 <= angle < 67.5: dir_str = "South-East"
            elif 67.5 <= angle < 112.5: dir_str = "South"
            elif 112.5 <= angle < 157.5: dir_str = "South-West"
            elif angle >= 157.5 or angle < -157.5: dir_str = "West"
            elif -157.5 <= angle < -112.5: dir_str = "North-West"
            elif -112.5 <= angle < -67.5: dir_str = "North"
            elif -67.5 <= angle < -22.5: dir_str = "North-East"
            else: dir_str = "Unknown"
            
            # Approximate steps (1 step = 16 units)
            steps_x = round(abs(dx) / 16)
            steps_y = round(abs(dy) / 16)
            
            nearby.append({
                "name": loc_name, 
                "distance": round(dist, 2),
                "direction": dir_str,
                "steps": {"x": steps_x, "y": steps_y}
            })
    nearby.sort(key=lambda x: x['distance'])
    return nearby[:3]

def load_zones():
    zones = {}
    z_path = r"d:\Projects\AI_Emu_Player\emulator\zones.txt"
    if os.path.exists(z_path):
        with open(z_path, "r") as f:
            for line in f:
                if ":" not in line: continue
                parts = line.strip().split()
                id_parts = parts[0].split(":")
                if len(id_parts) < 2: continue
                sub_ids = id_parts[1].split(",")
                name = " ".join(parts[1:])
                for sid_hex in sub_ids:
                    try:
                        dec = int(sid_hex, 16)
                        zones[dec] = name
                    except: pass
    return zones

def extract():
    proc = get_process()
    if not proc: return
    handle = ctypes.windll.kernel32.OpenProcess(0x10, False, proc.pid)
    
    zones = load_zones()
    try:
        from emulator.item_db import ITEM_DB
    except:
        ITEM_DB = {}
    
    spells_info = {}
    spells_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "spells_info.json")
    if os.path.exists(spells_path):
        with open(spells_path, "r", encoding="utf-8") as f:
            spells_info = json.load(f)
            
    combat_items = {}
    items_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "combat_items.json")
    if os.path.exists(items_path):
        with open(items_path, "r", encoding="utf-8") as f:
            combat_items = json.load(f)

    data = {
        "gold": 0, "map_id": 0, "map_name": "Unknown", "loc_type": "Dungeon", 
        "x": 0, "y": 0, "transport": "Walk", "nearby": [],
        "party": [], "char_stats": {}, "capsules": [],
        "inventory": [], "scenario": [], "maidens": 0,
        # The old 0xA305C6 "battle flag" turned out to be bogus.
        # Keep this extractor explicit and conservative until a verified
        # standalone battle source is wired in here.
        "in_battle": False
    }

    # Gold & Map
    data['gold'] = int.from_bytes(read_mem(handle, BASE_OFFSET + GOLD_ADDR, 3), 'little')
    map_id = int.from_bytes(read_mem(handle, BASE_OFFSET + MAP_ID_ADDR, 2), 'little')
    data['map_id'] = map_id
    data['map_name'] = zones.get(map_id, "Unknown Area")
    
    # Classification
    name_lower = data['map_name'].lower()
    if "overworld" in name_lower or "seafloor" in name_lower:
        data['loc_type'] = "Overworld"
    elif any(t in name_lower for t in ["elcid", "sundletan", "alunze", "tanbel", "clamento", "parcelyte", "gordovan", "merix", "bound", "aleyn", "gruberik", "narcysus", "treadool", "dankirk", "auralio", "ferim", "agurio", "treble", "portravia", "eserikto", "barnan", "durale", "chaed", "preamarl", "narvick"]):
        if not any(d in name_lower for d in ["cave", "tower", "dungeon", "shrine", "mountain", "laboratory"]):
            data['loc_type'] = "Town"
        else:
            data['loc_type'] = "Dungeon"
    else:
        data['loc_type'] = "Dungeon"

    # Coordinates
    if data['loc_type'] == "Overworld":
        t_flag = read_mem(handle, BASE_OFFSET + TRANSPORT_FLAG, 1)[0]
        if t_flag == 0xFF:
            data['transport'] = "Ship/Airship"
            addr_x, addr_y = SHIP_X_FAST, SHIP_Y_FAST
        else:
            data['transport'] = "Walk"
            addr_x, addr_y = WALK_X_FAST, WALK_Y_FAST
        
        # Exact 2-byte read as requested
        xf = read_mem(handle, BASE_OFFSET + addr_x, 1)[0]
        xs = read_mem(handle, BASE_OFFSET + addr_x + 1, 1)[0]
        yf = read_mem(handle, BASE_OFFSET + addr_y, 1)[0]
        ys = read_mem(handle, BASE_OFFSET + addr_y + 1, 1)[0]
        
        data['x'] = (xs << 8) | xf
        data['y'] = (ys << 8) | yf
        
        loc_data = load_json_data("data/locations.json")
        # Ensure MAP_SIZE=4000 in get_nearby_locations
        data['nearby'] = get_nearby_locations(data['x'], data['y'], loc_data)
        
    elif data['loc_type'] == "Town":
        data['x'] = int.from_bytes(read_mem(handle, BASE_OFFSET + TOWN_X, 2), 'little')
        data['y'] = int.from_bytes(read_mem(handle, BASE_OFFSET + TOWN_Y, 2), 'little')
    else:
        # Use existing DUNGEON offsets (High only for now if that's what we have)
        data['x'] = read_mem(handle, BASE_OFFSET + DUNGEON_X_HIGH, 1)[0]
        data['y'] = read_mem(handle, BASE_OFFSET + DUNGEON_Y_HIGH, 1)[0]

    # Characters
    names = ["Maxim", "Selan", "Guy", "Artea", "Tia", "Dekar", "Lexis"]
    slots = read_mem(handle, BASE_OFFSET + PARTY_SLOTS, 4)
    for sid in slots:
        if sid < 7:
            n = names[sid]
            data['party'].append(n)
            cb = BASE_OFFSET + CHAR_STATS_BASE + (sid * 0xBE)
            stats = read_mem(handle, cb, 0xC0) # Read up to IP offset (0xBF)
            ip_raw = stats[0xBF]
            ip_percent = round((ip_raw / 255.0) * 100)
            char_spells = []
            # Spell IDs are at 0x99 - 0xB8 (32 bytes)
            spell_bytes = stats[0x99:0xB9]
            for idx, s_id_raw in enumerate(spell_bytes):
                s_hex = f"{s_id_raw:02X}"
                if s_hex in spells_info:
                    s_meta = spells_info[s_hex]
                    if s_meta.get("combat", False):
                        char_spells.append({
                            "name": s_meta["name"],
                            "cost": s_meta["mp"],
                            "abs_idx": idx, # 0-indexed absolute position in spellbook
                            "desc": s_meta["description"]
                        })

            data['char_stats'][n] = {
                "level": stats[0x11],
                "hp": int.from_bytes(stats[0x14:0x16], 'little'),
                "max_hp": int.from_bytes(stats[0x28:0x2A], 'little'),
                "mp": int.from_bytes(stats[0x16:0x18], 'little'),
                "max_mp": int.from_bytes(stats[0x2A:0x2C], 'little'),
                "status": stats[0x12],
                "ip": ip_percent,
                "spells": char_spells
            }

    data['capsules'] = get_capsule_monsters(handle)

    # Inventory [ID] [QtyValue]
    # QtyValue // 2 is quantity.
    # QtyValue % 2 == 0: Even Item list.
    # QtyValue % 2 == 1: Odd Item list.
    inv_raw = read_mem(handle, BASE_OFFSET + INV_START, INV_END - INV_START + 1)
    item_counts = {}
    combat_inventory = []
    for i in range(0, len(inv_raw), 2):
        if i+1 >= len(inv_raw): break
        item_id = inv_raw[i]
        qty_val = inv_raw[i+1]
        
        if item_id in [0, 255] or qty_val == 0: continue
        
        qty = qty_val // 2
        suffix = "Even" if qty_val % 2 == 0 else "Odd"
        list_type = suffix.lower()
        key = f"{item_id:02X}_{suffix}"
        
        name = ITEM_DB.get(key, f"Unknown_{key}")
        if "Iris" in name: continue
        item_counts[name] = item_counts.get(name, 0) + qty

        # Combat filtering
        i_hex = f"{item_id:02X}"
        if i_hex in combat_items.get(list_type, {}):
            c_meta = combat_items[list_type][i_hex]
            combat_inventory.append({
                "name": name,
                "qty": qty,
                "abs_idx": i // 2, # Pos in 1-column menu
                "desc": c_meta.get("desc", ""),
                "target": c_meta.get("target", "Single")
            })

    data['inventory'] = [{"name": n, "qty": q} for n, q in item_counts.items()]
    data['combat_inventory'] = combat_inventory

    # Scenario
    scen_map = {0:"Door key", 1:"Shrine", 2:"Basement", 3:"Cloud", 4:"Dankirk", 5:"Flower", 6:"Ghost", 7:"Heart", 8:"Lake", 9:"Light", 10:"Magma", 11:"Narcysus", 12:"Ruby", 13:"Sky", 14:"Sword", 15:"Tree", 16:"Trial", 17:"Truth", 18:"Wind", 19:"Engine", 20:"Jade"}
    scen_bytes = read_mem(handle, BASE_OFFSET + SCENARIO_START, 3)
    val = int.from_bytes(scen_bytes, 'little')
    data['scenario'] = [name for bit, name in scen_map.items() if val & (1 << bit)]

    # Maidens
    try:
        flags_path = r"d:\Projects\Python\lufia2-autotracker-v1.4.5\src\data\dungeon_flags_snes9x.json"
        spoiler_data = load_json_data("emulator/spoiler.json")
        flags_map = load_json_data(flags_path)
        data['maidens'] = get_maiden_count(handle, spoiler_data, flags_map)
    except:
        data['maidens'] = 0

    with open("live_data.json", "w") as f: json.dump(data, f, indent=4)
    
    # Generate briefings
    try:
        from agent.intel_synthesizer import IntelSynthesizer
        syn = IntelSynthesizer()
        syn.generate_all(data)
    except Exception as e:
        print(f"Briefing gen error: {e}")

    print(f"SUCCESS: Extracted {data['map_name']} ({data['map_id']}) at ({data['x']}, {data['y']})")

if __name__ == "__main__":
    extract()
