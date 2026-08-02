import requests
import json
import logging
import os
import re
import numpy as np
from agent.llm.tactical_ledger import TacticalLedger
from agent.runtime_config import get_llm_api_url, get_llm_request_timeout

class NumpyJSONEncoder(json.JSONEncoder):
    """ Custom encoder for numpy types """
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)


class KoboldLLM:
    def __init__(self, api_url=None, request_timeout_seconds=None):
        self.api_url = api_url or get_llm_api_url()
        self.request_timeout_seconds = request_timeout_seconds or get_llm_request_timeout()
        
    def query(self, prompt, max_context_length=4096, max_length=600, temperature=0.1, grammar=None, stop_sequence=None):
        """
        Sends a prompt to the local KoboldCpp server.
        """
        payload = {
            "prompt": prompt,
            "max_context_length": max_context_length,
            "max_length": max_length,
            "temperature": temperature,
            "top_k": 40,
            "top_p": 0.9,
            "rep_pen": 1.1
        }
        if grammar:
            payload["grammar"] = grammar
        if stop_sequence:
            payload["stop_sequence"] = stop_sequence
        
        try:
            response = requests.post(self.api_url, json=payload, timeout=self.request_timeout_seconds)
            response.raise_for_status()
            data = response.json()
            return data["results"][0]["text"].strip()
        except requests.exceptions.RequestException as e:
            logging.error(f"LLM Connection Error (Is KoboldCpp running?): {e}")
            return None

from agent.state_monitor import GameStateMonitor
from agent.knowledge_manager import KnowledgeManager

class AgentBrain:
    def __init__(self, data_dirs=["data", "agent/memory"]):
        self.llm = KoboldLLM()
        self.state_monitor = GameStateMonitor()
        self.knowledge_manager = KnowledgeManager(data_dirs=data_dirs)
        self.short_term_memory = [] # Last N actions/observations
        self.cached_bundles = "" # Persists between cycles until cleared
        self.ledger = TacticalLedger()
        self.last_action_result = {}
        self.working_memory_path = os.path.join(os.path.dirname(__file__), "..", "memory", "working_memory.json")
        self.working_memory = self._load_working_memory()
        
    def clear_combat_context(self):
        self.cached_bundles = ""

    def _default_working_memory(self):
        return {
            "current_goal": "",
            "last_navigation_summary": "",
            "last_navigation_failure": "",
            "last_battle_result": "",
        }

    def _load_working_memory(self):
        try:
            if os.path.exists(self.working_memory_path):
                with open(self.working_memory_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = self._default_working_memory()
                if isinstance(data, dict):
                    merged.update(data)
                return merged
        except Exception as e:
            logging.error(f"Failed to load working memory: {e}")
        return self._default_working_memory()

    def _save_working_memory(self):
        try:
            os.makedirs(os.path.dirname(self.working_memory_path), exist_ok=True)
            with open(self.working_memory_path, "w", encoding="utf-8") as f:
                json.dump(self.working_memory, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to save working memory: {e}")

    def update_working_memory(self, **kwargs):
        changed = False
        for key, value in kwargs.items():
            if key in self.working_memory and self.working_memory.get(key) != value:
                self.working_memory[key] = value
                changed = True
        if changed:
            self._save_working_memory()

    def remember_goal(self, goal_text):
        self.update_working_memory(current_goal=str(goal_text or "").strip())

    def remember_navigation_result(self, action_result):
        if not isinstance(action_result, dict):
            return
        summary = str(action_result.get("summary") or "").strip()
        failure = summary if action_result.get("stalled") else ""
        self.update_working_memory(
            last_navigation_summary=summary,
            last_navigation_failure=failure,
        )

    def remember_battle_result(self, result_text):
        self.update_working_memory(last_battle_result=str(result_text or "").strip())

    def _normalize_command(self, command):
        if not command:
            return command
        c = str(command).strip()
        m = re.match(r'\[MOVE:\s*DIR\s*([NSEW])\s*\]', c, re.I)
        if m:
            d = {"N":"NORTH","S":"SOUTH","E":"EAST","W":"WEST"}[m.group(1).upper()]
            return f"[MOVE: {d} 1]"
        m = re.match(r'\[MOVE:\s*([NSEW])(?:\s+(\d+))?\s*\]', c, re.I)
        if m:
            d = {"N":"NORTH","S":"SOUTH","E":"EAST","W":"WEST"}[m.group(1).upper()]
            n = m.group(2) or "1"
            return f"[MOVE: {d} {n}]"
        if c.upper() == "[CMD: LEAVE_TOWN]":
            return "[NAV: Exit]"
        return c

    def add_to_memory(self, action, observation):
        self.short_term_memory.append({"action": action, "obs": observation})
        if len(self.short_term_memory) > 10:
            self.short_term_memory.pop(0)
            
    def ask_for_guidance(self, current_info, next_state):
        """
        Constructs a ChatML prompt with clear ROLE and RESPONSE FORMAT.
        """
        # 0. Update Synthesizer if in battle
        if current_info.get("in_battle"):
            try:
                from agent.intel_synthesizer import IntelSynthesizer
                syn = IntelSynthesizer()
                syn.generate_all(current_info)
            except Exception as e:
                logging.error(f"Failed to synthesize battle briefing: {e}")

        # Live Pulse (Highly Volatile)
        live_block = self.state_monitor.get_highly_volatile_block(current_info, next_state)
        in_battle = live_block.get("combat_state", {}).get("in_battle", False)
        
        # 1. System Prompt (ROLE)
        system_content = (
            "### ROLE\n"
            "You are the decision core for a local Lufia 2 agent. Be decisive, concrete, and recovery-focused.\n\n"
            "### HARD RULES\n"
            "1. Outside combat, keep one immediate objective and act toward it.\n"
            "2. If the last move failed or position did not change, do not repeat that same blocked move immediately.\n"
            "3. Prefer short, safe movement bursts. Use 1 to 4 tiles unless in a clear corridor.\n"
            "4. Do not request more info if current data already supports an action.\n"
            "5. Do not flee normal encounters by reflex. Only flee if survival is genuinely worse than fighting.\n"
            "6. Missing combat info is not danger evidence. If combat data is incomplete, do not panic-flee.\n"
            "7. If all four directions appear blocked, do not guess a random move. Prefer [INTERACT] or [PULL: BRIEFING].\n"
            "8. After a flee or battle end, re-establish route immediately. Do not spiral.\n"
            "9. During exploration, prefer frontier progress over perfect 100% room coverage unless progress stalls.\n\n"
            "### RESPONSE FORMAT\n"
            "You MUST respond with exactly this JSON format and nothing else:\n"
            '{ "rule_confirmation": "Options confirmed.", "thought": "Reasoning", "command": "[COMMAND]" }\n'
        )

        # 2. User Prompt (SITUATION & PULSE)
        situation_parts = []
        if in_battle:
            situation_parts.append("Location: Battle Encounter")
            situation_parts.append("Combat Environment: battle_briefing.md/battle_navigation.md active.")
            situation_parts.append("Enemy formation is a straight front line unless stated otherwise.")
            situation_parts.append(f"Battle State: {current_info.get('battle_state', 'PRE_BATTLE')}")
            if current_info.get("sub_state"):
                situation_parts.append(f"Battle Sub-State: {current_info.get('sub_state')}")
            if current_info.get("info_type"):
                situation_parts.append(f"Requested Battle Info: {current_info.get('info_type')}")
            if current_info.get("current_char_idx") is not None:
                situation_parts.append(f"Current Character Index: {current_info.get('current_char_idx')}")
                party = current_info.get("party", []) or []
                char_idx = current_info.get("current_char_idx")
                if isinstance(char_idx, int) and 0 <= char_idx < len(party):
                    current_char_name = party[char_idx]
                    situation_parts.append(f"Current Character: {current_char_name}")
                    char_data = current_info.get("char_stats", {}).get(current_char_name, {}) if current_char_name else {}
                    max_mp = int(char_data.get("max_mp", 0) or 0)
                    mp_now = int(char_data.get("mp", 0) or 0)
                    ip_now = int(char_data.get("ip", 0) or 0)
                    spells = char_data.get("spells", []) or []
                    ip_attacks = char_data.get("ip_attacks", []) or []
                    combat_items = current_info.get("combat_inventory", []) or []

                    if max_mp > 0:
                        situation_parts.append(f"Current Character MP: {mp_now}/{max_mp}")
                    else:
                        situation_parts.append("Current Character MP: N/A (natural non-caster)")
                        situation_parts.append("Hard Restriction: this character is a natural non-caster. [SPELL] is invalid on this turn.")
                    situation_parts.append(f"Current Character IP: {ip_now}%")
                    situation_parts.append("Rules Reminder: spells spend MP; IP attacks spend IP.")

                    if spells:
                        spell_slots = ", ".join(
                            f"#{spell.get('slot', (spell.get('abs_idx', 0) + 1))}: {spell.get('name', 'Unknown')} ({spell.get('cost', 0)} MP, {spell.get('category', 'Offensive')})"
                            for spell in spells[:12]
                        )
                        situation_parts.append(f"Spell Slots: {spell_slots}")
                        situation_parts.append("Spell slot numbers use the real in-game menu positions. Hidden non-combat spells may still count toward numbering.")
                    if ip_attacks:
                        ip_lines = []
                        for idx, ip_data in enumerate(ip_attacks[:6], start=1):
                            slot = ip_data.get("slot", idx)
                            name = ip_data.get("name", f"IP {idx}")
                            cost = ip_data.get("cost", "?")
                            availability = "ready" if ip_data.get("available", True) else "locked"
                            ip_lines.append(f"#{slot}: {name} ({cost} IP, {availability})")
                        situation_parts.append("Available IP: " + ", ".join(ip_lines))
                    if combat_items:
                        item_slots = ", ".join(
                            f"#{item.get('slot', 1)}: {item.get('name', 'Item')} x{item.get('qty', 1)}"
                            for item in combat_items[:12]
                        )
                        situation_parts.append(f"Combat Item Slots: {item_slots}")
            if current_info.get("sub_state") == "SWAP_PENDING":
                party = current_info.get("party", []) or []
                layout = list(party[:4])
                while len(layout) < 4:
                    layout.append("Empty")
                situation_parts.append("Swap Layout:\n1. " + layout[0] + "    2. " + layout[1] + "\n3. " + layout[2] + "    4. " + layout[3])
            if current_info.get("pending_action_type"):
                situation_parts.append(f"Targeting Action: {current_info.get('pending_action_type')}")
            if current_info.get("sub_state") == "ACTION_LOCKED" and current_info.get("pending_action_type"):
                locked_type = str(current_info.get("pending_action_type")).upper()
                situation_parts.append(f"Locked Intent: you already chose {locked_type}. Finish that choice before doing anything else.")
            enemies = current_info.get("enemies", []) or []
            if enemies:
                enemy_lines = []
                for idx, enemy in enumerate(enemies, start=1):
                    enemy_lines.append(f"- Enemy {idx}: {enemy.get('name', f'Enemy {idx}')} | HP {enemy.get('hp', '?')} | Pos {enemy.get('pos', 'Front')}")
                situation_parts.append("Enemy Summary:\n" + "\n".join(enemy_lines))
            else:
                situation_parts.append("Enemy Summary:\n- No enemy data currently available from live state.")
        else:
            loc_name = current_info.get("location_name") or current_info.get("map_name") or live_block.get("spatial", {}).get("location") or "Unknown"
            situation_parts.append(f"Location: {loc_name}")

            plan_state = current_info.get("plan_state")
            if plan_state:
                situation_parts.append(f"Plan State: {json.dumps(plan_state, cls=NumpyJSONEncoder)}")

            cmd_history = current_info.get("_cmd_history", [])
            history_str = "\n".join(f"- Turn -{len(cmd_history)-i}: {c}" for i, c in enumerate(cmd_history[-5:])) if cmd_history else "- (none yet)"
            situation_parts.append(f"Recent Commands:\n{history_str}")

            stm = self.short_term_memory[-3:]
            stm_str = "\n".join(f"- {m['action']} => {m['obs']}" for m in stm) if stm else "- none"
            situation_parts.append(f"Recent Action Memory:\n{stm_str}")

            if self.last_action_result:
                situation_parts.append(f"Last Action Result:\n{json.dumps(self.last_action_result, indent=2, cls=NumpyJSONEncoder)}")

        if not in_battle and self.cached_bundles:
            situation_parts.append(f"Knowledge Snippets:\n{self.cached_bundles}")
        if not in_battle:
            wm_lines = []
            if self.working_memory.get("current_goal"):
                wm_lines.append(f"- Current Goal: {self.working_memory['current_goal']}")
            if self.working_memory.get("last_navigation_summary"):
                wm_lines.append(f"- Last Navigation: {self.working_memory['last_navigation_summary']}")
            if self.working_memory.get("last_navigation_failure"):
                wm_lines.append(f"- Recent Failure To Avoid Repeating: {self.working_memory['last_navigation_failure']}")
            if self.working_memory.get("last_battle_result"):
                wm_lines.append(f"- Last Battle Result: {self.working_memory['last_battle_result']}")
            if wm_lines:
                situation_parts.append("Working Memory:\n" + "\n".join(wm_lines))

        user_content = f"### SITUATION\n" + "\n".join(situation_parts) + "\n\n"
        user_content += f"### LIVE PULSE\n{json.dumps(live_block, indent=2, cls=NumpyJSONEncoder)}\n\n"
        
        if in_battle:
            battle_state = current_info.get("battle_state", "PRE_BATTLE")
            sub_state = current_info.get("sub_state")
            is_boss = bool(current_info.get("is_boss"))
            party = current_info.get("party", []) or []
            char_idx = current_info.get("current_char_idx")
            current_char_name = party[char_idx] if isinstance(char_idx, int) and 0 <= char_idx < len(party) else None
            char_data = current_info.get("char_stats", {}).get(current_char_name, {}) if current_char_name else {}
            has_spells = bool(char_data.get("spells")) and char_data.get("max_mp", 0) > 0
            has_ip = bool(char_data.get("ip_attacks")) or int(char_data.get("ip", 0) or 0) > 0
            has_items = bool(current_info.get("combat_inventory"))
            living_enemy_count = len(current_info.get("enemies", []) or [])
            available_targets = [str(i) for i in range(1, min(living_enemy_count, 4) + 1)]
            if living_enemy_count > 1:
                available_targets.append("ALL")

            if battle_state == "PRE_BATTLE":
                if sub_state == "SWAP_PENDING":
                    user_content += "### CURRENT TURN\nAvailable: [TARGET]: [1], [TARGET]: [2], [TARGET]: [3], [TARGET]: [4]. Choose two slot numbers to swap.\n"
                else:
                    available_opts = ["[INFO]: PARTY", "[INFO]: ENEMIES", "[BATTLE: FIGHT]", "[BATTLE: SWAP]"]
                    if not is_boss:
                        available_opts.insert(3, "[BATTLE: FLEE]")
                    user_content += f"### CURRENT TURN\nAvailable: {', '.join(available_opts)}\n"
                    user_content += "Pre-battle rule: normally use only [BATTLE: FIGHT], [BATTLE: FLEE], or [BATTLE: SWAP]. Optional shorthand is allowed only for the first acting character if it maps to a real option, for example [BATTLE: FIREBALL] or [BATTLE: ATTACK]. If uncertain, use [BATTLE: FIGHT].\n"
            elif battle_state == "GATHERING_ACTIONS" and sub_state == "ACTION_LOCKED":
                pending_action_type = (current_info.get("pending_action_type") or "").upper()
                if pending_action_type == "IP":
                    ip_lines = []
                    for idx, ip_data in enumerate(char_data.get("ip_attacks", []) or [], start=1):
                        slot = ip_data.get("slot", idx)
                        name = ip_data.get("name", f"IP {idx}")
                        cost = ip_data.get("cost", "?")
                        availability = "ready" if ip_data.get("available", True) else "locked"
                        ip_lines.append(f"#{slot}: {name} ({cost} IP, {availability})")
                    user_content += "### CURRENT TURN\n"
                    user_content += "Sticky battle note: you already committed to an IP attack for this character.\n"
                    user_content += "Do not switch to [ATTACK], [SPELL], [ITEM], or [DEFEND] now. Reply only with [IP: n] or [CANCEL].\n"
                    if ip_lines:
                        user_content += "Known IP Slots: " + ", ".join(ip_lines) + "\n"
                    else:
                        user_content += "Known IP Slots: none parsed yet. Reply with [CANCEL] if you need to back out.\n"
                else:
                    user_content += "### CURRENT TURN\nAvailable: [CANCEL]. Finish the locked action or cancel it.\n"
            elif battle_state == "GATHERING_ACTIONS" and sub_state == "TARGETING":
                pending_action_type = (current_info.get("pending_action_type") or "").upper()
                attack_targets = [t for t in available_targets if t != "ALL"]
                target_text = ", ".join(available_targets) if available_targets else "ALL"
                if pending_action_type == "ATTACK":
                    attack_target_text = ", ".join(attack_targets) if attack_targets else "1"
                    user_content += (
                        f"### CURRENT TURN\nAvailable: [GROUP]: [ENEMY] and [TARGET]: [{attack_target_text}]. "
                        "Basic ATTACK is single-target unless a weapon effect says otherwise. "
                        "Do not repeat [ATTACK]. Reply only with target selection such as `[GROUP]: [ENEMY], [TARGET]: [1]` or shorthand `@ ENEMY 1`. "
                        "Dead or empty enemy slots are omitted from Enemy Summary.\n"
                    )
                elif pending_action_type == "SPELL":
                    chosen_spell = None
                    spell_option = str(current_info.get("pending_action_option") or "").strip()
                    if spell_option and current_char_name:
                        for spell in char_data.get("spells", []) or []:
                            if str(spell.get("slot", "")) == spell_option:
                                chosen_spell = spell
                                break
                    if chosen_spell:
                        spell_category = chosen_spell.get("category", "Offensive")
                        preferred_group = chosen_spell.get("preferred_group", "ENEMY")
                        user_content += (
                            f"### CURRENT TURN\nSelected Spell: #{chosen_spell.get('slot')} {chosen_spell.get('name')} "
                            f"({spell_category}, {chosen_spell.get('cost', 0)} MP). "
                        )
                        if preferred_group == "ENEMY":
                            user_content += (
                                f"Available: [GROUP]: [ENEMY] and [TARGET]: [{target_text}]. "
                                "Offensive or debuff spells should target enemies. Using offensive spells on PARTY is self-destructive and can cause a game over. "
                                "Do not repeat the spell command now. Reply only with target selection such as `[GROUP]: [ENEMY], [TARGET]: [1]` or shorthand `@ ENEMY 1`.\n"
                            )
                        else:
                            user_content += (
                                "Available: [GROUP]: [PARTY] and [TARGET]: [1, 2, 3, 4, ALL]. "
                                "Healing and buff spells should target allies, not enemies. "
                                "Do not repeat the spell command now. Reply only with target selection such as `[GROUP]: [PARTY], [TARGET]: [1]` or shorthand `@ PARTY 1`.\n"
                            )
                    else:
                        user_content += (
                            f"### CURRENT TURN\nAvailable: [GROUP]: [ENEMY or PARTY] and [TARGET]: [{target_text}]. "
                            "Do not repeat the action command now. Reply only with target selection.\n"
                        )
                else:
                    user_content += (
                        f"### CURRENT TURN\nAvailable: [GROUP]: [ENEMY or PARTY] and [TARGET]: [{target_text}]. "
                        "Do not repeat the action command now. Reply only with target selection. "
                        "Dead or empty enemy slots are omitted from Enemy Summary.\n"
                    )
            else:
                available_opts = ["[ATTACK]"]
                if has_spells:
                    available_opts.append("[SPELL: slot]")
                if has_ip:
                    available_opts.append("[IP]: [1-6]")
                if has_items:
                    available_opts.append("[ITEM: slot]")
                available_opts.extend(["[DEFEND]", "[CANCEL]"])
                user_content += f"### CURRENT TURN\nAvailable: {', '.join(available_opts)}\n"
                if not has_spells:
                    user_content += "Hard restriction: this current character cannot cast spells right now. Do not choose [SPELL].\n"
                if has_spells or has_ip or has_items:
                    user_content += "If you choose [SPELL], use the displayed spell slot number. Use [SPELL: n] or [SPELL]: [n]. For [IP] use a slot number. For [ITEM], use the displayed item slot number with [ITEM: n].\n"
                    if has_spells:
                        user_content += "Spell numbering follows the full in-game spell list, even when some non-combat spells are omitted from the display.\n"
                    if has_items:
                        user_content += "Item numbering follows the full in-game inventory order, even when only combat-usable items are shown here.\n"
                if living_enemy_count > 1 and (has_spells or has_ip or has_items):
                    user_content += "Tactical note: if you want to damage ALL enemies, prefer [SPELL], [IP], or [ITEM]. Basic [ATTACK] is usually single-target.\n"

            cmd_val_rule = 'string'
        else:
            user_content += "### CURRENT TURN\nAvailable: [MOVE: NORTH/SOUTH/EAST/WEST 1-4], [NAV: Exit or visible landmark], [INTERACT], [PULL: BRIEFING], [PULL: PUZZLE]\n"
            cmd_val_rule = '"\\"" "[" [^\\"]+ "\\""' 

        # 3. Construct ChatML Prompt
        prompt = (
            f"<|im_start|>system\n{system_content}<|im_end|>\n"
            f"<|im_start|>user\n{user_content}<|im_end|>\n"
            f"<|im_start|>assistant\n{{"
        )

        # GBNF Grammar with Strict Literal Rule Confirmation
        grammar = (
            'root   ::= rule-c "," ws thought "," ws command ws "}"\n'
            'rule-c ::= "\\"rule_confirmation\\"" ws ":" ws "\\"Options confirmed.\\""\n'
            'thought ::= "\\"thought\\"" ws ":" ws string\n'
            'command ::= "\\"command\\"" ws ":" ws ' + cmd_val_rule + '\n'
            'string  ::= "\\"" [^\\"]* "\\""\n'
            'ws      ::= [ \\t\\n]*'
        )

        stop_seq = ["\n###", "}", "<|im_end|>"]
        response_text = self.llm.query(prompt, temperature=0.1, grammar=grammar, stop_sequence=stop_seq)
        
        # Handle the fact that we started with "{"
        if response_text:
            if not response_text.startswith("{"):
                full_json = "{" + response_text
                # If we hit the stop sequence "}", it might not be in response_text
                if not full_json.endswith("}"):
                    full_json += "}"
            else:
                full_json = response_text
        else:
            return None

        # Parsing
        try:
            data = json.loads(full_json)
            thought = data.get("thought", "...")
            command = data.get("command", "...")
            
            logging.info(f"AI Thought: {thought}")
            
            if not in_battle:
                logging.info(f"LLM Directive: {command}")
                new_bundles = self.knowledge_manager.resolve_pull_requests(command)
                if new_bundles:
                    self.cached_bundles = new_bundles

            return command
        except Exception as e:
            logging.error(f"Failed to parse GBNF JSON: {e}")
            logging.debug(f"Raw Response Attempt: {full_json}")
            
            match = re.search(r'(\[(?:BATTLE|PULL|MOVE|NAV|INTERACT): [^\]]+\]|\[INTERACT\])', full_json)
            if match:
                command = self._normalize_command(match.group(1).upper())
                logging.warning(f"Fallback: Extracted command via Regex: {command}")
                return command
            return "### INVALID COMMAND ###"

if __name__ == "__main__":
    # Test connection
    brain = AgentBrain()
    print("Testing local KoboldCpp connection...")
    response = brain.ask_for_guidance({"location_name": "Test Room"}, {})
    print(f"LLM Response: {response}")
