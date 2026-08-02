import time
import logging
import json
import os
import sys
import re
import pydirectinput
from agent.rl.lufia_env import Lufia2Env
from agent.llm.kobold_interface import AgentBrain
from agent.rl.battle_macro import BattleMacroExecutor
from emulator.vision_helper import VisionHelper
from emulator.ip_menu_scanner import BattleIPMenuCache
from agent.rl.exploration_manager import ExplorationManager
from agent.intel_synthesizer import IntelSynthesizer

def sanitize_text(text):
    """Strips non-printable ASCII characters and excess whitespace."""
    if not isinstance(text, str):
        text = str(text)
    clean = re.sub(r'[^\x20-\x7E]', ' ', text)
    return " ".join(clean.split()).strip()

def load_zones(filepath="emulator/zones.txt"):
    zones = {}
    if not os.path.exists(filepath):
        logging.warning("zones.txt not found!")
        return zones
    with open(filepath, "r") as f:
        for line in f:
            if ":" not in line: continue
            parts = line.strip().split()
            id_str = parts[0].split(":")[0]
            name = " ".join(parts[1:])
            loc_type = "Dungeon"
            name_lower = name.lower()
            if "overworld" in name_lower or "seafloor" in name_lower:
                loc_type = "Overworld"
            elif any(t in name_lower for t in ["town", "kingdom", "village", "port", "island", "elcid", "sundletan", "alunze", "tanbel", "clamento", "parcelyte", "gordovan", "merix", "bound", "aleyn", "gruberik", "narcysus", "treadool", "dankirk", "auralio", "ferim", "agurio", "treble", "portravia", "eserikto", "barnan", "durale", "chaed", "preamarl", "narvick"]):
                if not any(d in name_lower for d in ["cave", "tower", "dungeon", "shrine", "mountain", "laboratory"]):
                    loc_type = "Town"
            try:
                dec_id = int(id_str, 16)
                zones[dec_id] = {"name": name, "type": loc_type}
            except: pass
    return zones

def load_navigation_data(filepath="data/map_navigation.json"):
    nav = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                nav = json.load(f)
        except Exception as e: logging.error(f"Failed to load map navigation data: {e}")
    return nav

def load_locations_logic(filepath="data/locations_logic.json"):
    logic = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                logic = json.load(f)
        except Exception as e: logging.error(f"Failed to load locations logic: {e}")
    return logic

def load_tactical_summary(filepath="data/Tactical Summary.json"):
    if not os.path.exists(filepath) or os.path.isdir(filepath): return {}
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
            return {item["location"].lower(): item for item in data.get("dungeon_walkthrough", [])}
    except Exception as e:
        logging.error(f"Failed to load tactical summary: {e}")
        return {}

def get_accessible_locations(logic_dict, inventory, keys, capsules):
    assets = [item['item_name'].lower() for item in inventory]
    assets.extend([k.lower() for k in keys])
    assets.extend([c.lower() for c in capsules])
    accessible = []
    for loc, data in logic_dict.items():
        rules = data.get("access_rules", [])
        if not rules:
            accessible.append(loc)
            continue
        for rule_option in rules:
            requirements = [r.strip().lower() for r in rule_option.split(",")]
            option_met = True
            for req in requirements:
                if not any(req in a for a in assets):
                    option_met = False
                    break
            if option_met:
                accessible.append(loc)
                break
    return accessible

def _parse_battle_group_target(goal_l):
    group = "PARTY"
    group_match = re.search(r'\[group\]\s*:\s*\[(enemy|party)\]', goal_l)
    if not group_match:
        group_match = re.search(r'\[group\s*:\s*(enemy|party)\]', goal_l)
    if not group_match and re.search(r'\[group\]\s*:\s*\[all\]', goal_l, re.IGNORECASE):
        return group, "ALL"
    if not group_match and re.search(r'\[group\s*:\s*all\]', goal_l, re.IGNORECASE):
        return group, "ALL"
    if group_match:
        group = group_match.group(1).upper()

    target_match = re.search(r'\[target\]\s*:\s*\[([^\]]+)\]', goal_l)
    if not target_match:
        target_match = re.search(r'\[target\s*:\s*([^\]]+)\]', goal_l)
    target = target_match.group(1).strip().upper() if target_match else None

    if not target:
        inline_match = re.search(r'@\s*(enemy|party)\s*(all|\d+)', goal_l, re.IGNORECASE)
        if not inline_match:
            inline_match = re.search(r'\b(enemy|party)\s*(all|\d+)\b', goal_l, re.IGNORECASE)
        if not inline_match:
            inline_match = re.search(r'\btarget\s+(enemy|party)\s*(all|\d+)\b', goal_l, re.IGNORECASE)
        if not inline_match:
            inline_match = re.search(r'\b(enemy|party)\s*#\s*(\d+)\b', goal_l, re.IGNORECASE)
        if inline_match:
            group = inline_match.group(1).upper()
            target = inline_match.group(2).upper()

    if not target:
        if re.search(r'\ball enemies\b|\benemy all\b|\ball enemy\b', goal_l, re.IGNORECASE):
            group = "ENEMY"
            target = "ALL"
        elif re.search(r'\ball allies\b|\bparty all\b|\ball party\b', goal_l, re.IGNORECASE):
            group = "PARTY"
            target = "ALL"
        else:
            lone_target_match = re.search(r'\btarget\s*(\d+|all)\b', goal_l, re.IGNORECASE)
            if lone_target_match:
                target = lone_target_match.group(1).upper()
    return group, target

def _target_to_index(target_value):
    if not target_value:
        return 0
    if target_value == "ALL":
        return 0
    return int(target_value) - 1 if target_value.isdigit() else 0

def _target_to_indices(target_value):
    if not target_value or str(target_value).upper() == "ALL":
        return []
    parts = re.findall(r'\d+', str(target_value))
    return [max(0, int(part) - 1) for part in parts]

def _extract_numeric_choice(text):
    match = re.search(r'\b(\d+)\b', str(text or ""))
    return match.group(1) if match else None

def _is_valid_ip_slot(value):
    if value is None:
        return False
    try:
        slot = int(str(value).strip())
    except (TypeError, ValueError):
        return False
    return 1 <= slot <= 6

def _parse_combat_action(goal_l):
    patterns = [
        r'\[(ATTACK|SPELL|IP|ITEM|DEFEND|CANCEL)\]\s*:\s*\[([^\]]+)\]',
        r'\[(ATTACK|SPELL|IP|ITEM|DEFEND|CANCEL)\]\s*:\s*([^,\n]+)',
        r'\[(ATTACK|SPELL|IP|ITEM|DEFEND|CANCEL)\s*:\s*([^\]]+)\]',
        r'\b(ATTACK|SPELL|IP|ITEM|DEFEND|CANCEL)\b\s*[:@]\s*([^,\n]+)',
        r'\[(ATTACK|SPELL|IP|ITEM|DEFEND|CANCEL)\]',
    ]
    for pattern in patterns:
        m = re.search(pattern, goal_l, re.IGNORECASE)
        if not m:
            continue
        action = m.group(1).upper()
        option = m.group(2).strip() if len(m.groups()) > 1 and m.group(2) is not None else None
        return action, option
    return None, None

def _normalize_combat_goal_text(goal_text):
    text = str(goal_text or "").strip()
    text = re.sub(r'^\[command\]\s*:\s*', '', text, flags=re.IGNORECASE).strip()
    return text

def _normalize_name_token(text):
    return re.sub(r'[^a-z0-9]+', '', str(text or "").lower())

def _extract_battle_shortcut_text(goal_text):
    match = re.search(r'\[battle\s*:\s*([^\]]+)\]', str(goal_text or ""), re.IGNORECASE)
    return match.group(1).strip() if match else ""

def _resolve_prebattle_shortcut(goal_text, info, current_char_name):
    raw = _extract_battle_shortcut_text(goal_text)
    if not raw:
        return None
    raw_l = raw.lower().strip()
    if raw_l in {"fight", "flee", "swap"}:
        return None

    char_data = (info.get("char_stats", {}) or {}).get(current_char_name, {}) if current_char_name else {}
    spells = char_data.get("spells", []) or []
    ip_attacks = char_data.get("ip_attacks", []) or []
    items = info.get("combat_inventory", []) or []

    if raw_l in {"attack", "[attack]"}:
        return {"type": "ATTACK", "option": None, "source": raw}

    if raw_l.startswith("spell:"):
        raw_l = raw_l.split(":", 1)[1].strip()
    if raw_l.startswith("item:"):
        raw_l = raw_l.split(":", 1)[1].strip()
    if raw_l.startswith("ip:"):
        raw_l = raw_l.split(":", 1)[1].strip()

    numeric_choice = _extract_numeric_choice(raw_l)
    normalized_raw = _normalize_name_token(raw_l)

    for spell in spells:
        slot = str(spell.get("slot", spell.get("abs_idx", 0) + 1))
        spell_name = str(spell.get("name", "")).strip()
        normalized_spell = _normalize_name_token(spell_name)
        if numeric_choice and slot == numeric_choice:
            return {"type": "SPELL", "option": slot, "source": raw}
        if normalized_raw and normalized_raw == normalized_spell:
            return {"type": "SPELL", "option": slot, "source": raw}
        if normalized_raw and normalized_raw in normalized_spell:
            return {"type": "SPELL", "option": slot, "source": raw}

    for ip_entry in ip_attacks:
        slot = str(ip_entry.get("slot", ""))
        ip_name = str(ip_entry.get("name", "")).strip()
        normalized_ip = _normalize_name_token(ip_name)
        if _is_valid_ip_slot(numeric_choice) and slot == numeric_choice:
            return {"type": "IP", "option": slot, "source": raw}
        if normalized_raw and normalized_raw == normalized_ip:
            return {"type": "IP", "option": slot, "source": raw}

    for item in items:
        slot = str(item.get("slot", 1))
        item_name = str(item.get("name", "")).strip()
        normalized_item = _normalize_name_token(item_name)
        if numeric_choice and slot == numeric_choice:
            return {"type": "ITEM", "option": slot, "source": raw}
        if normalized_raw and normalized_raw == normalized_item:
            return {"type": "ITEM", "option": slot, "source": raw}
        if normalized_raw and normalized_raw in normalized_item:
            return {"type": "ITEM", "option": slot, "source": raw}

    return None

def _looks_like_combat_command(goal_l):
    text = str(goal_l or "").strip().lower()
    if any(
        token in text for token in (
            "[cancel]",
            "[info]:",
            "[battle:",
            "[attack]",
            "[spell]",
            "[spell:",
            "[ip]",
            "[ip:",
            "[item]",
            "[item:",
            "[defend]",
            "[group",
            "[target",
        )
    ):
        return True
    if re.match(r'^(attack|spell|ip|item|defend|cancel|group|target|battle|info)\b', text):
        return True
    if re.search(r'@\s*(enemy|party)\s*(all|\d+)', text, re.IGNORECASE):
        return True
    return False

class CombatStateManager:
    def __init__(self):
        self.reset()
        self.is_boss = False
        self.pending_action = {}
        self.last_info_type = None
        
    def reset(self):
        self.state = "PRE_BATTLE" 
        self.sub_state = None      
        self.current_char_idx = 0
        self.gathered_actions = []
        self.swap_targets = []
        self.pending_action = {}
        self.last_info_type = None

    def advance(self, in_battle):
        if not in_battle:
            self.reset()
            self.is_boss = False

    def get_context(self):
        return {
            "battle_state": self.state,
            "sub_state": self.sub_state,
            "info_type": self.last_info_type,
            "current_char_idx": self.current_char_idx,
            "is_boss": self.is_boss,
            "available_options": self.get_options(),
            "pending_action_type": self.pending_action.get("type"),
            "pending_action_option": self.pending_action.get("option"),
        }

    def get_options(self):
        if self.state == "PRE_BATTLE":
            options = ["1. [INFO]: PARTY", "2. [INFO]: ENEMIES", "3. [BATTLE]: FIGHT", "5. [BATTLE]: SWAP"]
            if not self.is_boss: options.insert(3, "4. [BATTLE]: FLEE")
            return options
        elif self.state == "GATHERING_ACTIONS":
            return ["1. [ATTACK]", "2. [SPELL]", "3. [IP]", "4. [ITEM]", "5. [DEFEND]", "6. [CANCEL]"]
        return []

    def cancel_last(self):
        if self.state == "GATHERING_ACTIONS":
            if self.current_char_idx > 0:
                self.current_char_idx -= 1
                if self.gathered_actions: self.gathered_actions.pop()
            else: self.state = "PRE_BATTLE"
        self.sub_state = None
        self.swap_targets = []
        self.pending_action = {}

def run_agent_loop():
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting Lufia 2 AI Agent Loop...")
    
    env = Lufia2Env(render_mode="ansi")
    brain = AgentBrain(data_dirs=["data", "agent/memory"])
    vision = VisionHelper()
    explorer = ExplorationManager()
    intel_synthesizer = IntelSynthesizer()
    
    KEY_MAP = {
        0: 'up', 1: 'down', 2: 'left', 3: 'right', 
        4: 'x', 5: 'z', 6: 'a', 7: 'q', 8: 'w', 9: 's',
        10: 'shift'
    }
    macro_executor = BattleMacroExecutor(KEY_MAP)
    combat_state = CombatStateManager()
    battle_ip_cache = BattleIPMenuCache()
    
    map_data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emulator", "map_data.json")
    map_data = {}
    if os.path.exists(map_data_path):
        with open(map_data_path, "r") as f: map_data = json.load(f)

    ram_map_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ram_map.json")
    RAM_MAP = {}
    if os.path.exists(ram_map_path):
        with open(ram_map_path, "r", encoding="utf-8") as f:
            RAM_MAP = json.load(f)
        
    zones = load_zones(os.path.join(os.path.dirname(os.path.abspath(__file__)), "emulator", "zones.txt"))
    
    state, info = env.reset()
    info = env._get_info(refresh=True, wait_for_live=True, timeout_sec=2.0, poll_interval=0.05)
    info["vision_battle"] = vision.is_in_battle()
    was_in_battle = info.get("in_battle", False) or info["vision_battle"]
    steps_since_last_think = 100 if was_in_battle else 90
    
    current_goal = "Advance toward promising frontier and useful landmarks without forcing full 100% exploration."
    last_pos = (0, 0)
    steps_at_pos = 0
    
    def dungeon_reset_procedure():
        logging.info("PUZZLE MACRO: Resetting room...")
        macro_executor._press(10) # Select
        time.sleep(0.5)
        macro_executor._press(0)  # Up
        time.sleep(0.2)
        macro_executor._press(4)  # A
        time.sleep(1.5)
        macro_executor._press(5)  # B
        time.sleep(0.5)

    next_state = None
    in_battle = False
    v_battle = False
    _pending_move_dir = None   # Direction from last LLM command
    _pending_move_steps = 0    # Steps remaining to execute
    _last_llm_response = ""    # Full LLM response text (for move parsing)
    _post_battle_result = None # 'FLED' or 'DEFEATED', cleared after one LLM injection
    _pending_result_dismissal = False
    _pull_budget = 2           # Max consecutive PULL-only cycles before forced movement
    _cmd_history = []          # Last 5 commands issued by LLM

    # Direction → key mapping
    DIR_KEY = {"north": "up", "south": "down", "east": "right", "west": "left"}

    def _canonical_pos(data):
        if not isinstance(data, dict):
            return (0, 0)
        dx = data.get("dungeon_x")
        dy = data.get("dungeon_y")
        if dx is None or dy is None:
            dx = data.get("x", 0)
            dy = data.get("y", 0)
        return (int(dx or 0), int(dy or 0))

    def _canonical_loc(data):
        if not isinstance(data, dict):
            return "Unknown"
        return data.get("location_name") or data.get("map_name") or "Unknown"

    def _refresh_info():
        fresh = env._get_info(refresh=True, wait_for_live=False, timeout_sec=0.25, poll_interval=0.05)
        if isinstance(fresh, dict):
            battle_ip_cache.inject_into_info(fresh)
            return fresh
        return {}

    def _wait_for_wram_dump(timeout_sec=0.8, poll_interval=0.05):
        try:
            env.reader.get_latest_dump()
            env.reader.send_command("DUMP")
        except Exception:
            return None
        deadline = time.time() + max(0.2, timeout_sec)
        while time.time() < deadline:
            dump_hex = env.reader.get_latest_dump()
            if dump_hex:
                try:
                    return bytes.fromhex(dump_hex)
                except ValueError:
                    logging.warning("Post-combat: received malformed WRAM dump.")
                    return None
            time.sleep(poll_interval)
        return None

    def _decode_even_ascii(raw):
        data = raw[::2]
        return "".join(chr(b) if 32 <= b <= 126 else " " for b in data)

    def _battle_result_stage_from_dump(wram):
        if not wram:
            return None
        offsets = RAM_MAP.get("offsets", {})
        exp_start = int(str(offsets.get("BattleResultExpTextStart", "0x541C")), 16)
        gold_start = int(str(offsets.get("BattleResultGoldTextStart", "0x5744")), 16)

        exp_window = wram[exp_start : exp_start + 0x16]
        exp_text = sanitize_text(_decode_even_ascii(exp_window)).upper()
        gold_text = sanitize_text(_decode_even_ascii(wram[gold_start : gold_start + 16])).upper()
        pane_text = sanitize_text(_decode_even_ascii(wram[exp_start : gold_start + 16])).upper()

        if "GETS" in exp_text and "EXP" in exp_text:
            return "EXP"
        if "GOLD" in gold_text:
            return "GOLD"
        if not pane_text:
            return "CLEAR"
        return None

    def _peek_battle_result_stage(timeout_sec=0.35):
        return _battle_result_stage_from_dump(_wait_for_wram_dump(timeout_sec=timeout_sec))

    def _has_live_reader(data):
        if not isinstance(data, dict):
            return False
        if not data.get("_reader_ready"):
            return False
        if (data.get("_reader_packet_count") or 0) <= 0:
            return False
        return True

    def _poll_for_move_result(before_pos, max_polls=10, poll_sleep=0.08):
        latest = _refresh_info()
        latest_pos = _canonical_pos(latest)
        for _ in range(max_polls):
            if latest_pos != before_pos and latest_pos != (0, 0):
                break
            time.sleep(poll_sleep)
            probe = _refresh_info()
            probe_pos = _canonical_pos(probe)
            if probe_pos != (0, 0):
                latest = probe
                latest_pos = probe_pos
        return latest, latest_pos

    def _battle_signature(data):
        if not isinstance(data, dict):
            return (False, (), ())
        party_hp = tuple(int(s.get("hp", 0)) for s in (data.get("party_stats", []) or []))
        enemy_hp = tuple(int(e.get("hp", 0)) for e in (data.get("enemies", []) or []))
        return (bool(data.get("in_battle", False)), enemy_hp, party_hp)

    def _battle_has_resolved(data, vision_in_battle=False, previous_enemy_count=0):
        if not isinstance(data, dict):
            return False
        if _peek_battle_result_stage(timeout_sec=0.2) in ("EXP", "GOLD"):
            logging.info("Post-combat inference: battle result marker is visible.")
            return True
        live_in_battle = bool(data.get("in_battle", False) or vision_in_battle)
        if not live_in_battle:
            return True

        enemies = data.get("enemies")
        if previous_enemy_count > 0 and isinstance(enemies, list) and enemies and all(int(e.get("hp", 0) or 0) <= 0 for e in enemies):
            logging.info("Post-combat inference: all visible enemies are at 0 HP.")
            return True
        if previous_enemy_count > 0 and isinstance(enemies, list) and len(enemies) == 0:
            logging.info("Post-combat inference: all previously visible enemies are gone.")
            return True
        return False

    def _wait_for_battle_settle(start_signature, previous_enemy_count=0, max_wait_sec=20.0, poll_interval=0.35, settle_sec=1.2, min_wait_sec=4.0):
        deadline = time.time() + max_wait_sec
        started_at = time.time()
        observed_change = False
        stable_since = time.time()
        last_signature = start_signature
        latest = _refresh_info()

        while time.time() < deadline:
            vision_battle_now = vision.is_in_battle()
            latest["vision_battle"] = vision_battle_now
            if _battle_has_resolved(latest, vision_battle_now, previous_enemy_count):
                latest["in_battle"] = False
                return latest

            signature = _battle_signature(latest)
            if signature != last_signature:
                last_signature = signature
                observed_change = True
                stable_since = time.time()
            elif observed_change and (time.time() - stable_since) >= settle_sec and (time.time() - started_at) >= min_wait_sec:
                return latest

            time.sleep(poll_interval)
            latest = _refresh_info()

        latest["vision_battle"] = vision.is_in_battle()
        return latest

    def _dismiss_battle_results(max_wait_sec=6.0):
        deadline = time.time() + max_wait_sec
        latest = _refresh_info()
        saw_gold = False
        cycle_started = time.time()
        clear_checks = 0

        while time.time() < deadline:
            latest["vision_battle"] = vision.is_in_battle()
            result_stage = _peek_battle_result_stage(timeout_sec=0.45)
            if result_stage == "EXP":
                clear_checks = 0
                logging.info("Post-combat marker: EXP/level-up page detected; advancing result flow.")
                macro_executor._press(4, duration_sec=0.08, wait_after_sec=0.22)
            elif result_stage == "GOLD":
                saw_gold = True
                clear_checks = 0
                logging.info("Post-combat marker: GOLD result screen detected; confirming final result page.")
                macro_executor._press(4, duration_sec=0.08, wait_after_sec=0.50)
            elif result_stage == "CLEAR":
                logging.info("Post-combat marker: result pane is blank; treating result screen as gone.")
                return latest, True
            else:
                map_ready = not latest.get("in_battle", False) and not latest.get("vision_battle", False)
                if map_ready:
                    clear_checks += 1
                    if saw_gold or clear_checks >= 2:
                        return latest, True
                else:
                    clear_checks = 0

                if (time.time() - cycle_started) < 2.5:
                    logging.info("Post-combat marker: waiting for result pages to appear before sending input.")
                else:
                    logging.info("Post-combat marker: waiting for result pages; nudging with A.")
                    macro_executor._press(4, duration_sec=0.08, wait_after_sec=0.22)

            time.sleep(1.0)
            latest = _refresh_info()

        latest["vision_battle"] = vision.is_in_battle()
        if saw_gold or (not latest.get("in_battle", False) and not latest.get("vision_battle", False) and _canonical_pos(latest) != (0, 0)):
            logging.warning("Post-combat check: result dismissal timed out after progress; keeping result dismissal active.")
        return latest, False

    try:
        while True:
            if _pending_result_dismissal:
                info, cleared = _dismiss_battle_results(max_wait_sec=10.0)
                if cleared:
                    logging.info("Post-combat check: result handling complete, resuming exploration.")
                    _pending_result_dismissal = False
                    in_battle = False
                    v_battle = False
                    was_in_battle = False
                    combat_state.reset()
                    battle_ip_cache.clear_battle()
                    brain.clear_combat_context()
                    steps_since_last_think = 99
                else:
                    logging.warning("Post-combat check: result screen dismissal timed out; retrying.")
                continue

            # --- BATTLE CHECK first ---
            in_battle = info.get("in_battle", False)
            v_battle = vision.is_in_battle()

            if in_battle or v_battle:
                info = _refresh_info()
                info["in_battle"] = True
                info["vision_battle"] = v_battle
                info["battle_state"] = "combat"
                steps_since_last_think = 100
                _pending_move_steps = 0  # Cancel any pending move
            else:
                curr_pos = _canonical_pos(info)
                map_id   = info.get("map_id", 0)

                if not _has_live_reader(info):
                    if steps_since_last_think % 25 == 0:
                        logging.warning(
                            "WAITING FOR LIVE STATE: reader_ready=%s connected=%s packets=%s",
                            info.get("_reader_ready"),
                            info.get("_reader_connected"),
                            info.get("_reader_packet_count"),
                        )
                    _pending_move_steps = 0
                    time.sleep(0.05)
                    info = _refresh_info()
                    continue

                # ── Execute pending LLM movement burst ─────────────────────
                if _pending_move_steps > 0 and _pending_move_dir:
                    key = DIR_KEY.get(_pending_move_dir, "up")
                    before_packets = info.get("_reader_packet_count")
                    before_ready = info.get("_reader_ready")
                    before_connected = info.get("_reader_connected")
                    macro_executor._press_named_key(key)
                    time.sleep(0.08)
                    info, new_pos = _poll_for_move_result(curr_pos)
                    next_state = env.state if hasattr(env, "state") else next_state
                    after_packets = info.get("_reader_packet_count")
                    after_ready = info.get("_reader_ready")
                    after_connected = info.get("_reader_connected")

                    logging.info(
                        "MOVE TRACE dir=%s before=%s after=%s packets=%s->%s reader_ready=%s->%s connected=%s->%s",
                        _pending_move_dir,
                        curr_pos,
                        new_pos,
                        before_packets,
                        after_packets,
                        before_ready,
                        after_ready,
                        before_connected,
                        after_connected,
                    )

                    if new_pos == curr_pos or new_pos == (0, 0):
                        # Position didn't change → inferred wall / blocked movement
                        battle_contact = bool(info.get("in_battle", False) or vision.is_in_battle())
                        if battle_contact:
                            brain.last_action_result = {
                                "summary": f"Move {_pending_move_dir} triggered an encounter before position could update.",
                                "stalled": False,
                                "attempted_direction": _pending_move_dir,
                                "position_before": {"x": curr_pos[0], "y": curr_pos[1]},
                                "position_after": {"x": curr_pos[0], "y": curr_pos[1]}
                            }
                        else:
                            explorer.record_attempt(map_id, curr_pos[0], curr_pos[1], _pending_move_dir)
                            brain.last_action_result = {
                                "summary": f"Move {_pending_move_dir} failed; dungeon position unchanged.",
                                "stalled": True,
                                "attempted_direction": _pending_move_dir,
                                "position_before": {"x": curr_pos[0], "y": curr_pos[1]},
                                "position_after": {"x": curr_pos[0], "y": curr_pos[1]}
                            }
                        brain.remember_navigation_result(brain.last_action_result)
                        _pending_move_steps = 0
                        logging.debug(f"Wall inferred at ({curr_pos[0]},{curr_pos[1]}) dir={_pending_move_dir}")
                    else:
                        _pending_move_steps -= 1
                        explorer.record_visit(map_id, new_pos[0], new_pos[1])
                        brain.last_action_result = {
                            "summary": f"Move {_pending_move_dir} succeeded; dungeon position changed.",
                            "stalled": False,
                            "attempted_direction": _pending_move_dir,
                            "position_before": {"x": curr_pos[0], "y": curr_pos[1]},
                            "position_after": {"x": new_pos[0], "y": new_pos[1]}
                        }
                        brain.remember_navigation_result(brain.last_action_result)

                    curr_pos = new_pos if new_pos != (0, 0) else curr_pos

                else:
                    # No autonomous movement. Just refresh RAM/state directly.
                    info = _refresh_info()
                    new_pos = _canonical_pos(info)
                    if new_pos != (0, 0) and new_pos != curr_pos:
                        explorer.record_visit(map_id, new_pos[0], new_pos[1])
                        brain.last_action_result = {
                            "summary": "Position changed without an explicit move command.",
                            "stalled": False,
                            "attempted_direction": None,
                            "position_before": {"x": curr_pos[0], "y": curr_pos[1]},
                            "position_after": {"x": new_pos[0], "y": new_pos[1]}
                        }
                        brain.remember_navigation_result(brain.last_action_result)
                        curr_pos = new_pos

                # ── Sprite/landmark scanning (every 5 steps) ────────────────
                if steps_since_last_think % 5 == 0:
                    sprites = vision.get_visible_sprites(
                        current_tile_x=curr_pos[0],
                        current_tile_y=curr_pos[1]
                    )
                    for s in sprites:
                        explorer.record_landmark(map_id, s["tile_x"], s["tile_y"], s["sprite"])

                # Re-check battle after move
                in_battle = info.get("in_battle", False)
                v_battle = vision.is_in_battle()
                if in_battle or v_battle:
                    logging.info("BATTLE DETECTED mid-move! Forcing immediate LLM think.")
                    info["in_battle"] = True
                    info["battle_state"] = "combat"
                    steps_since_last_think = 100
                    _pending_move_steps = 0

                last_pos = curr_pos
                steps_since_last_think += 1

            was_in_battle = in_battle or v_battle

            if steps_since_last_think >= 100:
                logging.info(f"LLM Thinking... Goal: {current_goal}")
                info = _refresh_info()
                info["vision_battle"] = v_battle
                battle_ctx = vision.get_battle_context()
                info["battle_state"] = battle_ctx
                
                vision_says_battle = info.get("in_battle", False) or v_battle or battle_ctx != "none"
                lock_released = False
                vis_loc = vision.get_visual_localization(sanitize_text(zones.get(info.get('map_id', 0), {}).get("name", "Unknown")))
                if not vision_says_battle and vis_loc and vis_loc.get("confidence", 0) > 0.6:
                    info["in_battle"] = False
                    lock_released = True

                if (info.get("in_battle", False) or vision_says_battle) and not lock_released:
                    info["in_battle"] = True
                    round_committed = False
                    pre_round_enemy_count = len(info.get("enemies", []) or [])
                    round_start_signature = _battle_signature(info)
                    # COMBAT INTERACTION 
                    try:
                        while True:
                            combat_state.advance(True)
                            if not combat_state.is_boss:
                                boss_dir = os.path.join("emulator", "sprites", "bosses")
                                if os.path.exists(boss_dir):
                                    for b in os.listdir(boss_dir):
                                        if vision.match_template(os.path.join(boss_dir, b)) > 0.7:
                                            combat_state.is_boss = True
                                            break

                            full_ctx = info.copy()
                            full_ctx["in_battle"] = True
                            full_ctx["vision_battle"] = True
                            full_ctx.update(combat_state.get_context())
                            if combat_state.state == "GATHERING_ACTIONS":
                                party = info.get("party", [])
                                char_name = party[combat_state.current_char_idx] if combat_state.current_char_idx < len(party) else "Unknown"
                                char_data = info.get("char_stats", {}).get(char_name, {})

                                full_ctx.update({"spells": char_data.get("spells", []), "ip_attacks": char_data.get("ip_attacks", [])})
                            
                            intel_synthesizer.generate_location_briefing(full_ctx)
                            new_goal = brain.ask_for_guidance(full_ctx, None)
                            if not new_goal: break
                            normalized_goal = _normalize_combat_goal_text(new_goal)
                            goal_l = normalized_goal.lower()
                            logging.info(f"Combat: {new_goal}")

                            if not _looks_like_combat_command(goal_l):
                                logging.warning("Combat: ignoring non-combat command while battle is active: %s", new_goal)
                                continue

                            if "[cancel]" in goal_l:
                                combat_state.cancel_last()
                                continue
                            if "[info]:" in goal_l:
                                combat_state.sub_state = "INFO_PENDING"
                                combat_state.last_info_type = "PARTY" if "party" in goal_l else "ENEMIES"
                                continue

                            if combat_state.state == "PRE_BATTLE":
                                if combat_state.sub_state == "SWAP_PENDING":
                                    targets = re.findall(r'\[target\]:\s*\[(\d+)\]', goal_l)
                                    if targets:
                                        combat_state.swap_targets.extend(targets)
                                    elif "[battle: swap]" in goal_l:
                                        logging.info("Combat: swap menu already open; waiting for target slot numbers.")
                                        continue

                                    if len(combat_state.swap_targets) >= 2:
                                        t1, t2 = map(int, combat_state.swap_targets[:2])
                                        logging.info(f"Swap {t1} and {t2}")
                                        macro_executor.swap_positions(t1, t2)
                                        combat_state.sub_state = None
                                        combat_state.swap_targets = []
                                    continue

                                party = info.get("party", []) or []
                                first_actor = party[0] if party else None
                                prebattle_shortcut = None
                                if "[battle:" in goal_l and not any(tag in goal_l for tag in ("[battle: fight]", "[battle: flee]", "[battle: swap]")):
                                    prebattle_shortcut = _resolve_prebattle_shortcut(normalized_goal, info, first_actor)
                                    if prebattle_shortcut:
                                        logging.info(
                                            "Combat: resolved pre-battle shortcut %s for %s as %s %s.",
                                            new_goal,
                                            first_actor,
                                            prebattle_shortcut.get("type"),
                                            prebattle_shortcut.get("option"),
                                        )
                                        goal_l = "[battle: fight]"
                                    else:
                                        logging.info("Combat: coercing invalid pre-battle shortcut %s to [BATTLE: FIGHT].", new_goal)
                                        goal_l = "[battle: fight]"

                                if "[battle: fight]" in goal_l:
                                    macro_executor.start_combat_round("fight")
                                    time.sleep(0.4)
                                    combat_state.state = "GATHERING_ACTIONS"
                                    combat_state.sub_state = None
                                    combat_state.last_info_type = None
                                    combat_state.current_char_idx = 0
                                    combat_state.gathered_actions = []
                                    combat_state.pending_action = {}
                                    if prebattle_shortcut:
                                        combat_state.pending_action = {
                                            "type": prebattle_shortcut["type"],
                                            "option": prebattle_shortcut.get("option"),
                                        }
                                        if prebattle_shortcut["type"] == "IP":
                                            combat_state.sub_state = "TARGETING"
                                        elif prebattle_shortcut["type"] in {"SPELL", "ITEM", "ATTACK"}:
                                            combat_state.sub_state = "TARGETING"
                                        logging.info(
                                            "Combat: pre-battle shortcut queued first action for %s as %s %s.",
                                            first_actor,
                                            prebattle_shortcut["type"],
                                            prebattle_shortcut.get("option"),
                                        )
                                    continue
                                elif "[battle: flee]" in goal_l:
                                    if combat_state.is_boss: continue
                                    macro_executor.start_combat_round("flee")
                                    time.sleep(1.0)
                                    if vision.match_template("No_Escape.png"): combat_state.is_boss = True
                                    break
                                elif "[battle: swap]" in goal_l:
                                    macro_executor.open_swap_menu()
                                    combat_state.sub_state = "SWAP_PENDING"
                                    continue
                                continue

                            elif combat_state.state == "GATHERING_ACTIONS":
                                if combat_state.sub_state == "ACTION_LOCKED":
                                    locked_type = str(combat_state.pending_action.get("type") or "").upper()
                                    act_t, act_option = _parse_combat_action(goal_l)
                                    current_char_name = party[combat_state.current_char_idx] if combat_state.current_char_idx < len(party) else "Unknown"
                                    current_char_data = info.get("char_stats", {}).get(current_char_name, {})

                                    if "[cancel]" in goal_l:
                                        combat_state.sub_state = None
                                        combat_state.pending_action = {}
                                        continue

                                    if locked_type == "IP":
                                        ip_attacks = battle_ip_cache.get_live_for_character(current_char_name) or []
                                        if act_t != "IP":
                                            fallback_slot = _extract_numeric_choice(act_option or normalized_goal)
                                            if _is_valid_ip_slot(fallback_slot):
                                                logging.info(
                                                    "Combat: forcing locked IP selection for %s from mismatched reply %s -> slot %s.",
                                                    current_char_name,
                                                    new_goal,
                                                    fallback_slot,
                                                )
                                                act_option = fallback_slot
                                            else:
                                                logging.warning(
                                                    "Combat: expected an IP slot for %s, got %s; unlocking and re-querying action selection.",
                                                    current_char_name,
                                                    new_goal,
                                                )
                                                combat_state.sub_state = None
                                                combat_state.pending_action = {}
                                                continue
                                        if not _is_valid_ip_slot(act_option):
                                            logging.warning(
                                                "Combat: expected an IP slot from 1 to 6 for %s; unlocking and re-querying action selection.",
                                                current_char_name,
                                            )
                                            combat_state.sub_state = None
                                            combat_state.pending_action = {}
                                            continue
                                        chosen_ip = next((entry for entry in ip_attacks if str(entry.get("slot")) == str(act_option)), None)
                                        if not chosen_ip:
                                            logging.warning(
                                                "Combat: IP slot %s is not present for %s; unlocking and re-querying action selection.",
                                                act_option,
                                                current_char_name,
                                            )
                                            combat_state.sub_state = None
                                            combat_state.pending_action = {}
                                            continue
                                        if not chosen_ip.get("available", True):
                                            logging.warning(
                                                "Combat: IP slot %s for %s is unavailable; unlocking and re-querying action selection.",
                                                act_option,
                                                current_char_name,
                                            )
                                            combat_state.sub_state = None
                                            combat_state.pending_action = {}
                                            continue
                                        combat_state.sub_state = "TARGETING"
                                        combat_state.pending_action = {"type": "IP", "option": act_option}
                                        continue

                                    logging.warning("Combat: unsupported action lock state for %s; clearing.", locked_type)
                                    combat_state.sub_state = None
                                    combat_state.pending_action = {}
                                    continue

                                if combat_state.sub_state == "TARGETING":
                                    group, target = _parse_battle_group_target(goal_l)
                                    pending_type = str(combat_state.pending_action.get("type") or "").upper()
                                    if not target:
                                        act_t, act_option = _parse_combat_action(normalized_goal)
                                        if act_t and pending_type and act_t == pending_type and act_option:
                                            fallback_group, fallback_target = _parse_battle_group_target(str(act_option))
                                            if fallback_target:
                                                group, target = fallback_group, fallback_target
                                        elif act_t and pending_type and act_t != pending_type:
                                            logging.warning(
                                                "Combat: received %s while waiting for %s target selection; clearing pending action and re-querying.",
                                                act_t,
                                                pending_type,
                                            )
                                            combat_state.sub_state = None
                                            combat_state.pending_action = {}
                                            continue
                                    if target:
                                        combat_state.pending_action.update({"group": group, "target": target})
                                        current_action = dict(combat_state.pending_action)
                                        current_char_name = party[combat_state.current_char_idx] if combat_state.current_char_idx < len(party) else "Unknown"
                                        atype = current_action.get("type")
                                        if atype == "ATTACK" and target == "ALL":
                                            logging.info("COMBAT TARGET ADJUST: basic ATTACK cannot target ALL, defaulting to target 1.")
                                            target = "1"
                                            combat_state.pending_action["target"] = target
                                            current_action["target"] = target
                                        t_idx = _target_to_index(target)
                                        target_indices = _target_to_indices(target)
                                        is_all = target == "ALL"

                                        logging.info(
                                            "COMBAT EXECUTE: char=%s action=%s target_group=%s target=%s",
                                            current_char_name,
                                            current_action.get("type"),
                                            group,
                                            target,
                                        )

                                        executed = False
                                        if atype == "ATTACK":
                                            macro_executor.select_attack(t_idx)
                                            executed = True
                                        elif atype == "DEFEND":
                                            macro_executor.select_defend()
                                            executed = True
                                        elif atype == "SPELL":
                                            spells = info.get("char_stats", {}).get(current_char_name, {}).get("spells", [])
                                            slot_val = str(current_action.get("option") or "").strip()
                                            spell_obj = next(
                                                (s for s in spells if str(s.get("slot", s.get("abs_idx", 0) + 1)) == slot_val),
                                                None,
                                            )
                                            if spell_obj:
                                                preferred_group = str(spell_obj.get("preferred_group", "ENEMY")).upper()
                                                if group != preferred_group:
                                                    logging.info(
                                                        "COMBAT TARGET ADJUST: spell slot %s for %s prefers %s, overriding requested group %s.",
                                                        slot_val,
                                                        current_char_name,
                                                        preferred_group,
                                                        group,
                                                    )
                                                    group = preferred_group
                                                menu_row = int(spell_obj.get("menu_row", 0) or 0)
                                                is_right_column = bool(spell_obj.get("is_right_column", False))
                                                macro_executor.select_spell(
                                                    menu_row,
                                                    is_right_column=is_right_column,
                                                    target_idx=t_idx,
                                                    target_all=is_all,
                                                    target_indices=target_indices,
                                                )
                                                executed = True
                                            else:
                                                logging.warning("COMBAT EXECUTE: spell slot '%s' not found for %s", slot_val, current_char_name)
                                        elif atype == "ITEM":
                                            items = info.get("combat_inventory", [])
                                            item_opt = str(current_action.get("option") or "").strip()
                                            item_obj = None
                                            if item_opt.isdigit():
                                                item_obj = next((itm for itm in items if str(itm.get("slot", 1)) == item_opt), None)
                                            else:
                                                i_name = item_opt.lower()
                                                item_obj = next((itm for itm in items if itm['name'].lower() == i_name), None)
                                            if item_obj:
                                                menu_index = int(item_obj.get("menu_index", max(0, int(item_obj.get("slot", 1)) - 1)) or 0)
                                                macro_executor.select_item(menu_index, target_idx=t_idx, target_all=is_all, target_is_enemy=(group == "ENEMY"))
                                                executed = True
                                            else:
                                                logging.warning("COMBAT EXECUTE: item option '%s' not found in combat inventory", item_opt)
                                        elif atype == "IP":
                                            slot_val = current_action.get("option", "1")
                                            slot_idx = int(slot_val) if str(slot_val).isdigit() else 1
                                            macro_executor.select_ip_attack(slot_idx, t_idx, target_all=is_all)
                                            executed = True

                                        combat_state.sub_state = None
                                        combat_state.pending_action = {}
                                        if not executed:
                                            continue

                                        combat_state.gathered_actions.append(current_action)
                                        combat_state.current_char_idx += 1
                                        info = _refresh_info()
                                        # Use char_stats instead of party_stats if available/aligned
                                        party_stats_raw = info.get("party_stats", [])
                                        alive_c = len([s for s in party_stats_raw if s.get('hp', 0) > 0])
                                        if combat_state.current_char_idx >= alive_c:
                                            round_committed = True
                                            combat_state.state = "PRE_BATTLE"
                                            break
                                        continue
                                    logging.warning(
                                        "Combat: could not parse targeting command while waiting for %s target selection: %s",
                                        combat_state.pending_action.get("type"),
                                        new_goal,
                                    )
                                    continue

                            act_t, act_option = _parse_combat_action(goal_l)
                            if act_t:
                                if act_t in ["ATTACK", "SPELL", "IP", "ITEM", "DEFEND"]:
                                    if act_t == "DEFEND":
                                        current_char_name = party[combat_state.current_char_idx] if combat_state.current_char_idx < len(party) else "Unknown"
                                        logging.info("COMBAT EXECUTE: char=%s action=DEFEND", current_char_name)
                                        macro_executor.select_defend()
                                        combat_state.gathered_actions.append({"type": "DEFEND"})
                                        combat_state.current_char_idx += 1
                                        info = _refresh_info()
                                        party_stats_raw = info.get("party_stats", [])
                                        alive_c = len([s for s in party_stats_raw if s.get('hp', 0) > 0])
                                        if combat_state.current_char_idx >= alive_c:
                                            round_committed = True
                                            combat_state.state = "PRE_BATTLE"
                                            break
                                    else:
                                        current_char_name = party[combat_state.current_char_idx] if combat_state.current_char_idx < len(party) else "Unknown"
                                        current_char_data = info.get("char_stats", {}).get(current_char_name, {})
                                        if act_t == "SPELL":
                                            if not current_char_data.get("spells") or int(current_char_data.get("max_mp", 0) or 0) <= 0:
                                                logging.warning("Combat: %s cannot cast spells; re-querying current character.", current_char_name)
                                                continue
                                            if not act_option or not str(act_option).isdigit():
                                                logging.warning("Combat: SPELL requires a numeric spell slot; re-querying current character.")
                                                continue
                                        elif act_t == "IP":
                                            ip_attacks = battle_ip_cache.get_live_for_character(current_char_name)
                                            if not ip_attacks:
                                                ip_attacks = battle_ip_cache.ensure_character_ip_attacks(
                                                    env.reader,
                                                    macro_executor,
                                                    current_char_name,
                                                    int(current_char_data.get("ip", 0) or 0),
                                                )
                                                if ip_attacks:
                                                    info.setdefault("char_stats", {}).setdefault(current_char_name, {})["ip_attacks"] = ip_attacks
                                                    combat_state.sub_state = "ACTION_LOCKED"
                                                    combat_state.pending_action = {"type": "IP"}
                                                    logging.info("Combat: scanned live IP pane for %s; locking follow-up to IP slot selection.", current_char_name)
                                                else:
                                                    logging.warning("Combat: failed to scan live IP pane for %s.", current_char_name)
                                                continue

                                            if not _is_valid_ip_slot(act_option):
                                                combat_state.sub_state = "ACTION_LOCKED"
                                                combat_state.pending_action = {"type": "IP"}
                                                logging.info("Combat: IP menu known for %s; locking follow-up to a concrete IP slot.", current_char_name)
                                                continue

                                            chosen_ip = next((entry for entry in ip_attacks if str(entry.get("slot")) == str(act_option)), None)
                                            if not chosen_ip:
                                                combat_state.sub_state = "ACTION_LOCKED"
                                                combat_state.pending_action = {"type": "IP"}
                                                logging.warning("Combat: IP slot %s is not present for %s; keeping IP selection locked.", act_option, current_char_name)
                                                continue
                                            if not chosen_ip.get("available", True):
                                                combat_state.sub_state = "ACTION_LOCKED"
                                                combat_state.pending_action = {"type": "IP"}
                                                logging.warning("Combat: IP slot %s for %s is currently unavailable; keeping IP selection locked.", act_option, current_char_name)
                                                continue
                                        elif act_t == "ITEM" and not act_option:
                                            logging.warning("Combat: %s requires an explicit option; re-querying current character.", act_t)
                                            continue
                                        combat_state.sub_state = "TARGETING"
                                        combat_state.pending_action = {"type": act_t, "option": act_option}
                                    continue
                            break
                    except Exception as ce:
                        logging.error(f"COMBAT LOOP ERROR: {ce}")
                        macro_executor.cancel_action(1)
                        break

                    # Re-verify battle truly ended before re-triggering LLM think.
                    if round_committed:
                        logging.info("Post-combat check: waiting for battle phase to settle.")
                        info = _wait_for_battle_settle(
                            round_start_signature,
                            previous_enemy_count=pre_round_enemy_count,
                            max_wait_sec=20.0,
                        )
                    else:
                        time.sleep(1.2)
                        info = _refresh_info()
                        info["vision_battle"] = vision.is_in_battle()

                    v_battle_post = info.get("vision_battle", vision.is_in_battle())
                    result_stage_post = _peek_battle_result_stage(timeout_sec=0.25)
                    battle_resolved = _battle_has_resolved(
                        info,
                        v_battle_post,
                        pre_round_enemy_count if round_committed else 0,
                    )
                    if result_stage_post in ("EXP", "GOLD"):
                        battle_resolved = True
                    in_battle_post = (info.get("in_battle", False) or v_battle_post) and not battle_resolved

                    if in_battle_post:
                        # Still in battle (flee failed, or new encounter immediately)
                        logging.info("Post-combat check: still in battle, re-triggering combat.")
                        info["in_battle"] = True
                        steps_since_last_think = 100
                    else:
                        # Battle truly over — determine how it ended
                        logging.info("Post-combat check: battle ended, entering result dismissal state.")
                        info["in_battle"] = False
                        _pending_result_dismissal = True
                        # Mark result: did we flee or defeat?
                        _post_battle_result = "FLED" if "flee" in str(current_goal).lower() else "DEFEATED"
                        if _post_battle_result == "DEFEATED":
                            last_result = getattr(brain, "last_action_result", {}) or {}
                            attempted_direction = str(last_result.get("attempted_direction") or "").lower()
                            pos_before = last_result.get("position_before") or {}
                            if attempted_direction and "encounter" in str(last_result.get("summary") or "").lower():
                                explorer.record_defeated_encounter(
                                    info.get("map_id", 0),
                                    pos_before.get("x", 0),
                                    pos_before.get("y", 0),
                                    attempted_direction,
                                )
                        brain.remember_battle_result(_post_battle_result)
                    continue

                # Exploration: build context, call LLM, parse movement commands
                map_id = info.get('map_id', 0)
                curr_x, curr_y = _canonical_pos(info)

                # Build exploration context and inject into info for the briefing
                explore_ctx = explorer.get_context_for_llm(map_id, curr_x, curr_y)
                explorer.decay_heatmap(map_id)
                info['exploration_context'] = explore_ctx

                # Inject post-battle situational awareness once after combat ends
                if _post_battle_result:
                    tool_items = [t for t in info.get('tool_items', []) if t in
                                  ('Arrow', 'Fire Arrow', 'Hook', 'Hammer')]
                    post_ctx = (
                        f"BATTLE RESULT: {_post_battle_result}. "
                        f"The enemy encounter has ended. "
                    )
                    if _post_battle_result == "FLED":
                        post_ctx += (
                            "WARNING: The enemy sprite is still present on the map. "
                            "Consider: (A) Step away at least one tile then walk back INTO the enemy sprite to re-engage and defeat it permanently (not guaranteed to trigger, but likely), "
                            "(B) Navigate around it if another route exists, "
                        )
                        if tool_items:
                            post_ctx += (
                                f"(C) Use {' or '.join(tool_items)} (Select menu) to stun the enemy on the map, "
                                "then walk past it while it is stunned. "
                            )
                        post_ctx += "Repeated fleeing from the same enemy wastes time and risks re-engagement."
                    info['post_battle_context'] = post_ctx
                    logging.info(f"Post-battle: {post_ctx}")
                    _post_battle_result = None  # Clear after one injection
                else:
                    info.pop('post_battle_context', None)

                # Auto-inject puzzle solution if stuck too long (no waiting for LLM to ask)
                if explore_ctx.get('auto_pull_puzzle'):
                    logging.info("PUZZLE STUCK: Auto-injecting puzzle solution.")
                    puzzle_data = brain.knowledge_manager.resolve_pull_requests("[PULL: PUZZLE]")
                    brain.cached_bundles = puzzle_data
                    explorer.reset_stuck(map_id)
                
                # Auto-inject BRIEFING if nothing is cached (prevents blind start)
                if not brain.cached_bundles:
                    logging.info("CONTEXT EMPTY: Auto-pulling BRIEFING for first turn.")
                    brain.cached_bundles = brain.knowledge_manager.resolve_pull_requests("[PULL: BRIEFING]")

                # Pass budget to info so it appears in the instructions text
                info['_pull_budget'] = _pull_budget

                # If pull budget is exhausted, force a heatmap movement this cycle
                if _pull_budget <= 0:
                    logging.info(f"PULL BUDGET EXHAUSTED: forcing heatmap movement instead of LLM call.")
                    best_dir = explorer.get_preferred_frontier_direction(map_id, curr_x, curr_y)
                    _pending_move_dir = best_dir
                    _pending_move_steps = 2
                    _pull_budget = 2  # reset
                    steps_since_last_think = 0
                    continue

                new_goal = brain.ask_for_guidance(info, next_state)
                _last_llm_response = new_goal or ""
                if new_goal:
                    _cmd_history.append(new_goal.strip())
                    if len(_cmd_history) > 5:
                        _cmd_history.pop(0)
                    info['_cmd_history'] = _cmd_history

                    nav_ctx = info.get('exploration_context', {}) or {}
                    blocked_dirs = set((nav_ctx.get('blocked_directions') or []))
                    all_blocked = blocked_dirs == {"north", "south", "east", "west"}
                    last_result = getattr(brain, 'last_action_result', {}) or {}
                    last_failed_dir = str(last_result.get('attempted_direction') or '').lower()
                    probe_match = re.search(r'\[MOVE:\s*(NORTH|SOUTH|EAST|WEST)', new_goal.upper())
                    requested_dir = probe_match.group(1).lower() if probe_match else None
                    if requested_dir and all_blocked:
                        logging.info("Navigation veto: all directions blocked in context; replacing movement with [INTERACT].")
                        new_goal = '[INTERACT]'
                        current_goal = new_goal
                    elif requested_dir and requested_dir in blocked_dirs:
                        logging.info(f"Navigation veto: {requested_dir} is marked blocked; suppressing illegal move.")
                        new_goal = '[INTERACT]' if nav_ctx.get('nearby_landmarks') else '[PULL: BRIEFING]'
                        current_goal = new_goal
                    elif requested_dir and requested_dir == last_failed_dir and last_result.get('stalled'):
                        logging.info(f"Navigation veto: repeated failed direction {requested_dir}; forcing re-evaluation.")
                        new_goal = '[PULL: BRIEFING]'

                    if new_goal.startswith("[MOVE:") or new_goal.startswith("[NAV:"):
                        current_goal = "Advance toward promising frontier and useful landmarks without forcing full 100% exploration."
                    elif new_goal == "[INTERACT]":
                        current_goal = "Check nearby objects or landmarks that may open progress."
                    elif new_goal == "[PULL: PUZZLE]":
                        current_goal = "Resolve the current puzzle room and reopen progress."
                    elif new_goal == "[PULL: BRIEFING]":
                        current_goal = "Refresh route context and choose a better frontier."
                    else:
                        current_goal = new_goal

                    brain.remember_goal(current_goal)

                    # --- Parse movement commands from LLM response ---
                    import re as _re
                    _had_movement = False

                    # [MOVE: NORTH 12] or [MOVE: NORTH]
                    move_match = _re.search(
                        r'\[MOVE:\s*(NORTH|SOUTH|EAST|WEST)(?:\s+(\d+))?\]',
                        new_goal.upper()
                    )
                    if move_match:
                        _pending_move_dir = move_match.group(1).lower()
                        _pending_move_steps = min(4, int(move_match.group(2))) if move_match.group(2) else 2
                        _had_movement = True
                        _pull_budget = 2  # movement issued → reset budget
                        logging.info(f"LLM Move: {_pending_move_dir} x{_pending_move_steps}")

                    # [NAV: LandmarkType] — walk toward nearest registered landmark
                    nav_match = _re.search(r'\[NAV:\s*([^\]]+)\]', new_goal)
                    if nav_match:
                        nav_target = nav_match.group(1).strip()
                        # Find landmark type key by label match
                        from agent.rl.exploration_manager import ExplorationManager as _EM
                        sprite_key = None
                        for k, (label, _) in _EM.LANDMARK_LABELS.items():
                            if nav_target.lower() in label.lower() or nav_target.lower() in k.lower():
                                sprite_key = k
                                break
                        if sprite_key:
                            lm = explorer.get_nearest_landmark(map_id, curr_x, curr_y, sprite_key)
                            if lm:
                                dx = lm['x'] - curr_x
                                dy = lm['y'] - curr_y
                                if abs(dx) >= abs(dy):
                                    _pending_move_dir = "east" if dx > 0 else "west"
                                    _pending_move_steps = max(1, min(4, abs(dx)))
                                else:
                                    _pending_move_dir = "south" if dy > 0 else "north"
                                    _pending_move_steps = max(1, min(4, abs(dy)))
                                _had_movement = True
                                _pull_budget = 2
                                logging.info(f"LLM NAV: heading {_pending_move_dir} x{_pending_move_steps} toward {sprite_key}")

                    # [INTERACT] — press A once
                    if "[INTERACT]" in new_goal.upper():
                        logging.info("LLM INTERACT: pressing A")
                        macro_executor._press(4)  # A button
                        time.sleep(0.3)
                        info = _refresh_info()
                        pos_after = _canonical_pos(info)
                        brain.last_action_result = {
                            "summary": "Interaction attempted.",
                            "stalled": False,
                            "attempted_direction": None,
                            "position_before": {"x": curr_x, "y": curr_y},
                            "position_after": {"x": pos_after[0] or curr_x, "y": pos_after[1] or curr_y}
                        }
                        brain.remember_navigation_result(brain.last_action_result)
                        _had_movement = True
                        _pull_budget = 2
                        steps_since_last_think = 99

                    # [reset room] — puzzle reset
                    if "reset room" in new_goal.lower():
                        dungeon_reset_procedure()
                        explorer.reset_stuck(map_id)
                        _pull_budget = 2
                        continue

                    # Decrement pull budget if LLM only requested info (no movement)
                    if not _had_movement:
                        _pull_budget = max(0, _pull_budget - 1)
                        logging.debug(f"PULL-only cycle, budget remaining: {_pull_budget}")

                # Save exploration memory periodically
                explorer.save_memory()
                steps_since_last_think = 0
            
            done = isinstance(info, dict) and info.get("is_game_over", False)
            if done: state, info = env.reset()
            was_in_battle = info.get("in_battle", False)
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        logging.info("Shut down.")
        env.close()

if __name__ == "__main__":
    run_agent_loop()
