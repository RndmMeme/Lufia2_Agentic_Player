import json
import logging
import os
import numpy as np

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

class GameStateMonitor:
    """
    Manages the split between Static, Volatile, and Highly Volatile game state.
    Reduces prompt noise by only including 'Volatile' data when it has meaningfully changed.
    """
    def __init__(self, persistence_path="agent/memory/last_volatile_state.json"):
        self.persistence_path = persistence_path
        self.last_volatile = self._load_last_state()
        
    def _load_last_state(self):
        if os.path.exists(self.persistence_path):
            try:
                with open(self.persistence_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Failed to load last volatile state: {e}")
        return {}

    def _save_state(self, state):
        try:
            with open(self.persistence_path, "w") as f:
                json.dump(state, f, indent=4, cls=NumpyJSONEncoder)
        except Exception as e:
            logging.error(f"Failed to save volatile state: {e}")

    def _categorize_items(self, inventory):
        cats = {
            "Healing": [],
            "Recover": [],
            "Utility": [],
            "Offense": [],
            "Remedy": [],
            "Revival": []
        }
        for i in inventory:
            name = i["name"].lower()
            qty = i.get("qty", 1)
            entry = f"{i['name']} (x{qty})"
            
            if any(kw in name for kw in ["potion"]):
                cats["Healing"].append(entry)
            elif any(kw in name for kw in ["magic", "jar"]):
                cats["Recover"].append(entry)
            elif any(kw in name for kw in ["escape", "warp"]):
                cats["Utility"].append(entry)
            elif any(kw in name for kw in ["boomerang", "dragon tooth", "ball"]):
                cats["Offense"].append(entry)
            elif any(kw in name for kw in ["antidote", "awake", "shriek", "mystery pin", "remedy"]):
                cats["Remedy"].append(entry)
            elif any(kw in name for kw in ["miracle", "regain"]):
                cats["Revival"].append(entry)
                
        # Filter out empty categories
        return {k: v for k, v in cats.items() if v}

    def get_static_block(self):
        """Tier 1: Strategy Blueprint. Sent every time."""
        return {
            "identity": "Expert AI playing Lufia 2: Rise of the Sinistrals (SNES).",
            "global_goal": "Defeat Daos in Daos' Shrine. Define and pursue an IMMEDIATE sub-goal that makes progress toward this. Only commit to travel to Daos' Shrine when all required conditions are met.",
            "prompt_strategy": [
                "1. Define a concrete IMMEDIATE objective (dungeon clear, item, rescue, etc.) before planning travel.",
                "2. Use `[PULL: BRIEFING]` for a condensed situational overview (Location, Party, Readiness).",
                "3. Use `[PULL: ITEM_SHOP]`, `[PULL: WEAPON_SHOP]`, or `[PULL: SPELL_SHOP]` when in towns.",
                "4. Use `[PULL: BATTLE]` only during combat for live HP/position data.",
                "5. Use `[CMD: LEAVE_TOWN]` to get the nearest exit when finished in a city."
            ],
            "controls": {
                "A (o)": "Interact / Confirm",
                "B (p)": "Cancel / Run (World Map)",
                "X (Menu)": "Open Menu",
                "Y (l)": "Use Tool",
                "Select (space)": "Tool Menu (Dungeons: Reset/Arrow/Hook)"
            }
        }

    def process_volatile_state(self, current_info):
        """
        Tier 2: Growth & Tactics. 
        Returns the Volatile block ONLY if significant changes occur.
        """
        # Precise fields defined by User
        party_stats = current_info.get("party_stats", [])
        scen = current_info.get("scenario", [])
        cleared = current_info.get("cleared_dungeons", [])
        inv = current_info.get("inventory", [])
        
        # Extract subset of Volatile info
        current_volatile = {
            "team_levels": [p.get("Level") for p in party_stats],
            "primary_stats": [{
                "name": p.get("name"), 
                "ATP": p.get("Atp"), 
                "DFP": p.get("Dfp"),
                "MGR": p.get("Mgr")
            } for p in party_stats],
            "gear": [i["name"] for i in inv if i.get("is_equip")],
            "keys_and_maidens": [k for k in scen if any(kw in k.lower() for kw in ["key", "maiden", "ruby", "water", "earth"])],
            "tools": [i["name"] for i in inv if i.get("is_tool")],
            "categorized_inventory": self._categorize_items(inv),
            "dungeon_progress": cleared,
            "sub_goal": current_info.get("current_sub_goal", "Clear current accessible dungeon.")
        }

        # Check for significant changes
        changed = False
        if not self.last_volatile:
            changed = True
        else:
            # Check Level/Stats
            if current_volatile["team_levels"] != self.last_volatile.get("team_levels"):
                changed = True
            # Check Progress
            if len(current_volatile["keys_and_maidens"]) != len(self.last_volatile.get("keys_and_maidens", [])):
                changed = True
            # Check Clear Flags
            if len(current_volatile["dungeon_progress"]) != len(self.last_volatile.get("dungeon_progress", [])):
                changed = True
            # Goal change
            if current_volatile["sub_goal"] != self.last_volatile.get("sub_goal"):
                changed = True

        if changed:
            self.last_volatile = current_volatile
            self._save_state(current_volatile)
            return current_volatile
        
        return None

    def get_highly_volatile_block(self, current_info, next_state):
        """Tier 3: Live Pulse. Sent every time."""
        # next_state may be None during exploration (no env.step called this cycle)
        if next_state is not None:
            in_battle = bool(next_state[8]) or current_info.get("vision_battle", False)
        else:
            in_battle = current_info.get("in_battle", False) or current_info.get("vision_battle", False)

        # Build per-character HP/MP summary so LLM knows who is healthy vs drained.
        # Format: "Name: HP_cur/HP_max HP, MP_cur/MP_max MP"
        party_vitals = {}
        for name, stats in current_info.get("char_stats", {}).items():
            hp_cur = stats.get("hp", "?")  
            hp_max = stats.get("max_hp", "?")
            mp_cur = stats.get("mp", "?")
            mp_max = stats.get("max_mp", "?")
            ip_pct = stats.get("ip", 0)
            if isinstance(mp_max, (int, float)) and mp_max == 0:
                mp_summary = "No MP by design (natural non-caster)"
            else:
                mp_summary = f"{mp_cur}/{mp_max} MP"
            party_vitals[name] = f"{hp_cur}/{hp_max} HP, {mp_summary}, {ip_pct}% IP"

        # Location: show name only, not raw map_id.
        location_name = current_info.get("location_name") or current_info.get("map_name") or "Unknown"

        spatial = {"location": location_name}
        if in_battle:
            spatial = {"status": "In Combat"}

        pulse = {
            "spatial": spatial,
            "combat_state": {
                "in_battle": in_battle,
                "enemy_formation": "Enemies line up left-to-right in front of the party by default.",
                "party_vitals": party_vitals,
                "ailments": current_info.get("status_ailments", [])
            },
            "visual_sight": {
                "detected_objects": [f"{s['type']} at {s['direction']}" for s in current_info.get("vision_sprites", [])],
                "screen_text": current_info.get("vision_text", ""),
                "localization": current_info.get("vision_localization", {})
            }
        }

        # Navigation/Exploration context (heatmap, walls, stuck state)
        if not in_battle:
            pulse["navigation_context"] = current_info.get("exploration_context", {})

        # Show post-battle result once (FLED/DEFEATED) with enemy persistence warning
        post_battle = current_info.get("post_battle_context")
        if post_battle:
            pulse["post_battle_alert"] = post_battle

        return pulse
