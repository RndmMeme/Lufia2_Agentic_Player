import json
import os

class IntelSynthesizer:
    def __init__(self, data_dir="data/mockups", logic_path="data/locations_logic.json", cities_path="data/cities.json", nav_path="data/map_navigation.json", shop_path="data/shop_data.json"):
        self.data_dir = data_dir
        self.logic_path = logic_path
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        
        self.logic = {}
        if os.path.exists(logic_path):
            with open(logic_path, 'r', encoding='utf-8') as f:
                self.logic = json.load(f)
        
        self.cities = {}
        if os.path.exists(cities_path):
            with open(cities_path, 'r', encoding='utf-8') as f:
                self.cities = json.load(f)

        self.nav_data = {}
        if os.path.exists(nav_path):
            with open(nav_path, 'r', encoding='utf-8') as f:
                self.nav_data = json.load(f)

        self.shop_data = {}
        if os.path.exists(shop_path):
            with open(shop_path, 'r', encoding='utf-8') as f:
                self.shop_data = json.load(f)

    def is_clearable(self, loc_name, scenario_items):
        if loc_name not in self.logic:
            return "Unknown"
        
        rules = self.logic[loc_name].get("access_rules", [])
        if not rules:
            return "Yes"
        
        for rule_group in rules:
            requirements = [r.strip() for r in rule_group.split(',')]
            if all(req in scenario_items for req in requirements):
                return "Yes"
        return "Not yet"

    def get_nearest_poi(self, map_id, curr_x, curr_y, poi_type_keyword):
        pois = self.nav_data.get(str(map_id), {}).get("pois", [])
        if not pois: return None
        
        best_poi = None
        min_dist = float('inf')
        
        for p in pois:
            if poi_type_keyword.lower() in p['name'].lower():
                dist = abs(p['x'] - curr_x) + abs(p['y'] - curr_y)
                if dist < min_dist:
                    min_dist = dist
                    best_poi = p
        
        if best_poi:
            steps = round(min_dist / 16)
            # Calculate direction
            dx = best_poi['x'] - curr_x
            dy = best_poi['y'] - curr_y
            dir_str = ""
            if dy < -8: dir_str += "North"
            elif dy > 8: dir_str += "South"
            if dx < -8: dir_str += "West"
            elif dx > 8: dir_str += "East"
            if not dir_str: dir_str = "here"
            
            return {"name": best_poi['name'], "steps": steps, "direction": dir_str, "x": best_poi['x'], "y": best_poi['y']}
        return None

    def generate_party_status(self, data):
        lines = ["# [TEAM: STATUS]", f"**Gold**: {data.get('gold', 0):,}", ""]
        lines.append("## Party Vitals")
        lines.append("| Character | Level | HP | MP | IP | Status |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        
        max_lvl = 0
        for name, stats in data.get('char_stats', {}).items():
            lvl = stats.get('level', 1)
            max_lvl = max(max_lvl, lvl)
            ip_val = stats.get('ip', 0)
            max_mp = stats.get('max_mp', 0)
            if max_mp == 0:
                mp_text = "N/A (natural non-caster)"
            else:
                mp_text = f"{stats['mp']}/{max_mp}"
            lines.append(f"| **{name}** | {lvl} | {stats['hp']}/{stats['max_hp']} | {mp_text} | {ip_val}% / 100% | OK |")

        lines.append("")
        lines.append("> [!NOTE]")
        lines.append("> `N/A (natural non-caster)` means the character is not expected to use magic. This is normal, not an MP shortage.")
        lines.append("")
        caps = data.get('capsules', [])
        lines.append(f"**Capsule Monsters**: {', '.join(caps) if caps else 'None'}")
        
        if data.get('in_battle', False):
            # NO Strategic Inventory during battle - keep it strictly tactical vitals
            with open(os.path.join(self.data_dir, "party_status.md"), "w") as f:
                f.write("\n".join(lines))
            return

        lines.append("")
        lines.append("## Strategic Note")
        lines.append("> [!NOTE]")
        if max_lvl <= 30:
            lines.append("> **Recovery Priority**: Level is low/mid (<=30). Potions are highly effective.")
        else:
            lines.append("> **Recovery Priority**: Level is high (>30). Focus on Hi-Potions and Spells.")
            
        with open(os.path.join(self.data_dir, "party_status.md"), "w") as f:
            f.write("\n".join(lines))

    def generate_location_briefing(self, data):
        in_battle = data.get('in_battle', False)
        battle_state = data.get('battle_state', 'PRE_BATTLE')
        char_idx = data.get('current_char_idx', 0)
        party = data.get('party', [])
        current_char = party[char_idx] if char_idx < len(party) else "Unknown"
        char_stats = data.get('char_stats', {}).get(current_char, {})
        has_mp = char_stats.get('max_mp', 0) > 0

        if in_battle:
            sub_state = data.get('sub_state')
            is_boss = data.get('is_boss', False)
            enemies = data.get('enemies', [])
            
            lines = [
                "### [CRITICAL STATE: FULL COMBAT MODE ACTIVE] ###",
                f"## STAGE: {battle_state}",
                "" if not sub_state else f"## SUB-SELECTION: {sub_state}",
                "",
                "> [!IMPORTANT]",
                "> YOU ARE IN BATTLE. Use ONLY the specified [BATTLE: ...], [INFO: ...], [TARGET: ...], or [GROUP: ...] tags.",
                ""
            ]

            if battle_state == 'PRE_BATTLE':
                if sub_state == 'INFO_PENDING':
                    # Info was requested, show it and ask for next step
                    info_type = data.get('info_type', 'PARTY')
                    if info_type == 'PARTY':
                        lines.append("### [INFO]: PARTY STATUS RECAP")
                        for name, stats in data.get('char_stats', {}).items():
                            max_mp = stats.get('max_mp', 0)
                            if max_mp == 0:
                                mp_text = "No MP by design (natural non-caster)"
                            else:
                                mp_text = f"{stats['mp']}/{max_mp} MP"
                            lines.append(f"- **{name}**: {stats['hp']}/{stats['max_hp']} HP, {mp_text}, {stats.get('ip', 0)}% / 100% IP")
                    else:
                        lines.append("### [INFO]: ENEMY BRIEFING RECAP")
                        for e in enemies:
                            lines.append(f"- {e['name']} | HP: {e['hp']} | Pos: {e.get('pos', 'Front')}")
                    lines.append("\n**Info provided. What do you want to do next?**")
                
                elif sub_state == 'SWAP_PENDING':
                    lines.append("### [BATTLE]: SWAP - SELECT TARGETS")
                    lines.append("The current party layout is:")
                    # 1 2 / 3 4 layout
                    party_names = [p if p else "Empty" for p in party]
                    # Ensure at least 4 slots for display
                    while len(party_names) < 4: party_names.append("Empty")
                    
                    lines.append(f"1. {party_names[0]}    2. {party_names[1]}")
                    lines.append(f"3. {party_names[2]}    4. {party_names[3]}")
                    lines.append("\nState who you want to trade places: `[TARGET]: [Number]` and `[TARGET]: [Number]`.")
                    lines.append("(Example: `[TARGET]: [1]` and `[TARGET]: [3]`)")
                
                else:
                    lines += [
                        "### ROUND START OPTIONS",
                        "Choose one of the following to begin the round:",
                        "1. `[INFO]: PARTY` - Provide party status briefing.",
                        "2. `[INFO]: ENEMIES` - Provide enemy briefing.",
                        "3. `[BATTLE]: FIGHT` - Start selecting character actions.",
                    ]
                    if not is_boss:
                        lines.append("4. `[BATTLE]: FLEE` - Attempt to escape the battle.")
                    lines.append("5. `[BATTLE]: SWAP` - Change character positions.")
                    lines.append("**Pre-Battle Rule**: Usually use only `[BATTLE]: FIGHT`, `[BATTLE]: FLEE`, or `[BATTLE]: SWAP`. A shorthand like `[BATTLE]: FIREBALL` or `[BATTLE]: ATTACK` is allowed only if it clearly refers to the first acting character's real options; otherwise use FIGHT.")
            
            elif battle_state == 'GATHERING_ACTIONS':
                if sub_state == 'ACTION_LOCKED':
                    action_type = str(data.get('pending_action_type', '')).upper()
                    lines.append(f"### [BATTLE]: {action_type} - LOCKED FOLLOW-UP")
                    lines.append("You already committed to this action. Do not switch action types now.")
                    if action_type == "IP":
                        lines.append("Reply only with a concrete IP slot such as `[IP: 1]` or use `[CANCEL]`.")
                        ip_list = []
                        for idx, i in enumerate(data.get('ip_attacks', []), start=1):
                            if isinstance(i, dict):
                                slot = i.get('slot', idx)
                                name = i.get('name', f'IP Move {idx}')
                                cost = i.get('cost', '?')
                                status = "ready" if i.get("available", True) else "locked"
                            else:
                                slot = idx
                                name = str(i) if i else f'IP Move {idx}'
                                cost = '?'
                                status = "unknown"
                            ip_list.append(f"{slot}: {name}({cost}IP, {status})")
                        if ip_list:
                            lines.append("**Known IP Slots**: " + ", ".join(ip_list))
                    else:
                        lines.append("Use `[CANCEL]` if you need to back out and choose a new action.")

                elif sub_state == 'TARGETING':
                    action_type = data.get('pending_action_type', 'ATTACK')
                    lines.append(f"### [BATTLE]: {action_type} - SELECT TARGET")
                    lines.append("Only provide target selection here. Do not repeat the action command.")
                    if str(action_type).upper() == "ATTACK":
                        lines.append("\n1. **Choose Group**: `[GROUP]: [ENEMY]` only for normal attacks.")
                    else:
                        lines.append("\n1. **Choose Group**: `[GROUP]: [ENEMY]` or `[GROUP]: [PARTY]`")
                    
                    enemy_count = len(enemies)
                    lines.append(f"\n2. **Choose Target(s)** (There are {enemy_count} enemies):")
                    lines.append("- `[TARGET]: [SINGLE]` (state one number)")
                    if str(action_type).upper() != "ATTACK":
                        lines.append("- `[TARGET]: [MULTIPLE]` (state at least 2 numbers)")
                        lines.append("- `[TARGET]: [ALL]`")
                    lines.append("- Shorthand also allowed: `@ ENEMY 1`, `@ ENEMY ALL`, `@ PARTY 1`")

                    lines.append("\n3. **Cancel**: `[CANCEL]` (Change target or abort action)")
                
                else:
                    lines += [
                        f"### SELECT ACTION FOR: **{current_char}**",
                        "1. `[ATTACK]` - Normal physical strike.",
                    ]
                    if not has_mp:
                        lines.append("**Hard Restriction**: This character is a natural non-caster. Do NOT choose `[SPELL]`.")
                    if has_mp:
                        lines.append("2. `[SPELL: n]` - Cast a specific spell by slot number from the list below.")
                    
                    lines += [
                        "3. `[IP]: [1-6]` - Use a specific IP slot.",
                        "4. `[ITEM: n]` - Use a specific combat item by slot number.",
                        "5. `[DEFEND]` - Guard for the turn.",
                        "6. `[CANCEL]` - Go back to previous character or Pre-Battle.",
                        ""
                    ]
                    
                    # Provide details for selection
                    if data.get('spells'):
                        spell_list = ", ".join(
                            [f"#{s.get('slot', s.get('abs_idx', 0) + 1)} {s['name']}({s['cost']}MP, {s.get('category', 'Offensive')})" for s in data['spells']]
                        )
                        lines.append("**Available Spells**: " + spell_list)
                        lines.append("**Spell Slot Rule**: Slot numbers follow the real in-game spell menu. Omitted non-combat spells still count toward numbering.")
                        lines.append("**Spell Safety Rule**: Offensive and debuff spells should target ENEMY. Casting offensive spells on PARTY is self-destructive and can cause a game over.")
                    if data.get('ip_attacks'):
                        ip_list = []
                        for idx, i in enumerate(data['ip_attacks'], start=1):
                            if isinstance(i, dict):
                                slot = i.get('slot', idx)
                                name = i.get('name', f'IP Move {idx}')
                                cost = i.get('cost', '?')
                            else:
                                slot = idx
                                name = str(i) if i else f'IP Move {idx}'
                                cost = '?'
                            ip_list.append(f"{slot}: {name}({cost}IP)")
                        lines.append("**Available IP (Slots 1-6)**: " + ", ".join(ip_list))
                    if data.get('combat_inventory'):
                        item_list = [f"#{i.get('slot', 1)} {i['name']}x{i['qty']}" for i in data['combat_inventory']]
                        lines.append("**Combat Items**: " + ", ".join(item_list))
                        lines.append("**Item Slot Rule**: Slot numbers follow the real in-game inventory order. Omitted non-combat items may still count toward numbering.")
                    if len(enemies) > 1 and (data.get('spells') or data.get('ip_attacks') or data.get('combat_inventory')):
                        lines.append("**AoE Hint**: If you want to hit all enemies, prefer `[SPELL]`, `[IP]`, or `[ITEM]`. Basic `[ATTACK]` is usually single-target.")

            lines += [
                "## Combat Command Protocol (FORCE FOLLOW)",
                "1. Provide reasoning.",
                "2. Provide standard tags exactly as requested.",
                "3. Use `[CANCEL]` to backtrack if necessary.",
                ""
            ]

            with open(os.path.join(self.data_dir, "location_briefing.md"), "w") as f:
                f.write("\n".join(lines))
            return

        lines = ["# [LOC: CURRENT BRIEFING]", ""]
        map_id = data.get('map_id', 0)
        try:
            lines.append(f"- **Area**: {data['map_name']} (ID: {int(map_id):04X})")
        except (ValueError, TypeError):
            lines.append(f"- **Area**: {data['map_name']}")
        lines.append(f"- **Type**: {data['loc_type']}")
        
        if data['loc_type'] == "Overworld":
            lines.append(f"- **Transport**: {data['transport']}")

        lines.append("")
        lines.append("## Navigation Note")
        lines.append("> [!TIP]")
        if data['loc_type'] == "Overworld":
            lines.append(f"You are in the **Overworld**. Move toward nearby locations to explore.")
        elif data['loc_type'] == "Town":
            lines.append(f"You are inside **{data['map_name']}**. Use `[NAV: Exit]` to find the exit.")
        else:
            lines.append(f"You are inside **{data['map_name']}**. Use `[MOVE: NORTH/SOUTH/EAST/WEST 1-4]` to explore, `[INTERACT]` to activate objects, `[NAV: Exit or visible landmark]` to walk toward a known landmark.")

        # ── Town POIs (only in towns) ──────────────────────────────────────────
        if data['loc_type'] == "Town":
            lines.append("")
            lines.append("### Town POIs")
            for poi_key in ["Priest", "Inn", "Shop", "Spell"]:
                found = self.get_nearest_poi(map_id, data['x'], data['y'], poi_key)
                if found:
                    lines.append(f"- **Nearest {poi_key}**: {found['name']} at ({found['x']}, {found['y']}) is ~{found['steps']} steps **{found['direction']}**.")

        # ── Dungeon Awareness (only in dungeons) ──────────────────────────────
        elif data['loc_type'] not in ("Overworld",):
            explore_ctx = data.get('exploration_context')
            if explore_ctx:
                lines.append("")
                lines.append("### Dungeon Awareness")
                tile = explore_ctx.get("tile", {})
                lines.append(f"- **Position**: Tile ({tile.get('x','?')}, {tile.get('y','?')})")
                lines.append(f"- **Tiles Explored**: {explore_ctx.get('tiles_explored', 0)}")
                best_dir = str(explore_ctx.get('best_unexplored_direction', '?') or '?').upper()
                lines.append(f"- **Best Direction to Explore**: {best_dir}")

                policy = explore_ctx.get("exploration_policy")
                if policy:
                    lines.append(f"- **Exploration Policy**: {policy}")

                navigation_mode = explore_ctx.get("navigation_mode")
                if navigation_mode:
                    lines.append(f"- **Navigation Mode**: {str(navigation_mode).replace('_', ' ').title()}")
                
                blocked = explore_ctx.get("blocked_directions", [])
                if blocked:
                    lines.append(f"- **Blocked Directions**: {', '.join(b.upper() for b in blocked)}")

                backtrack_dir = explore_ctx.get("immediate_backtrack_direction")
                if backtrack_dir:
                    lines.append(f"- **Immediate Backtrack To Avoid Unless Needed**: {str(backtrack_dir).upper()}")

                route_memory = explore_ctx.get("route_memory", {})
                if route_memory:
                    lines.append("")
                    lines.append("#### Route Memory")
                    lines.append(f"- **Current Segment**: {route_memory.get('current_segment', 'unknown')}")
                    lines.append(f"- **Segments Known**: {route_memory.get('segment_count', 0)}")
                    lines.append(f"- **Junctions Known**: {route_memory.get('junction_count', 0)}")
                    lines.append(f"- **Dead Ends Known**: {route_memory.get('dead_end_count', 0)}")
                    lines.append(f"- **Unfinished Branches**: {route_memory.get('unfinished_branch_count', 0)}")

                frontier_summary = explore_ctx.get("frontier_summary", [])
                if frontier_summary:
                    lines.append("")
                    lines.append("#### Frontier Options")
                    for item in frontier_summary[:3]:
                        direction = str(item.get("direction", "?")).upper()
                        score = item.get("score", 0)
                        reasons = ", ".join(item.get("reasons", []))
                        lines.append(f"- **{direction}**: score {score} ({reasons})")

                minimap = explore_ctx.get("local_minimap")
                if minimap:
                    lines.append("")
                    lines.append("#### Local Minimap")
                    lines.append("```")
                    lines.append("C=current  .=visited  ?=frontier  L=landmark")
                    lines.append(str(minimap))
                    lines.append("```")
                
                landmarks = explore_ctx.get("nearby_landmarks", [])
                if landmarks:
                    lines.append("")
                    lines.append("#### Visible Landmarks")
                    for lm in landmarks[:6]:  # Cap at 6 for brevity
                        puzzle_tag = " *(puzzle element)*" if lm.get("is_puzzle_element") else ""
                        lines.append(f"- **{lm['label']}**: {lm['direction']}, ~{lm['dist_tiles']} tiles away{puzzle_tag}")
                
                # Puzzle hint warning
                stuck = explore_ctx.get("stuck_cycles", 0)
                if explore_ctx.get("puzzle_hint_active"):
                    lines.append("")
                    lines.append("> [!WARNING]")
                    lines.append(f"> You have been wandering the same area for **{stuck} consecutive cycles**.")
                    lines.append("> This may be a puzzle room. Use `[PULL: PUZZLE]` to retrieve the solution for this dungeon.")
                    if explore_ctx.get("has_puzzle_elements"):
                        lines.append("> **Puzzle elements detected nearby** (lever, pillar, or switch). Interact with them using `[INTERACT]`.")

        # ── Overworld nearby locations ─────────────────────────────────────────
        if data.get('nearby'):
            lines.append("")
            lines.append("### Nearby Locations (Overworld)")
            for n in data['nearby']:
                name = n['name']
                dist = n['distance']
                direction = n.get('direction', 'Unknown')
                total_steps = round(dist / 16)
                is_town = name in self.cities
                warp_str = "Yes" if is_town else "No"
                
                if is_town:
                    lines.append(f"- **{name}**: ~{total_steps} steps **{direction}**. (Warp-able: **{warp_str}**)")
                else:
                    status = self.is_clearable(name, data.get('scenario', []))
                    lines.append(f"- **{name}**: ~{total_steps} steps **{direction}**. (Clearable: {status}, Warp-able: **{warp_str}**)")

        with open(os.path.join(self.data_dir, "location_briefing.md"), "w") as f:
            f.write("\n".join(lines))


    def generate_mission_readiness(self, data):
        if data.get('in_battle', False):
            # Silence mission data during battle to keep prompt focused
            with open(os.path.join(self.data_dir, "mission_readiness.md"), "w") as f:
                f.write("# [MISSION: SUSPENDED]\n\nCombat is active. Mission objectives are secondary to survival.")
            return

        lines = ["# [TEAM: MISSION READINESS]", ""]
        lines.append(f"- **Maidens**: {data.get('maidens', 0)} / 3")
        lines.append(f"- **Transport**: {data.get('transport', 'Walk')}")
        
        lines.append("")
        lines.append("## Key Progress")
        scen = data.get('scenario', [])
        for s in scen:
            lines.append(f"- {s}: Owned")
        
        lines.append("")
        lines.append("## Tactical Note")
        lines.append("> [!IMPORTANT]")
        if data.get('maidens', 0) < 3:
            lines.append(f"> Only {data.get('maidens', 0)}/3 Maidens retrieved. Continue exploring.")
        else:
            lines.append("> All Maidens retrieved. Ready for Daos' Shrine.")

        with open(os.path.join(self.data_dir, "mission_readiness.md"), "w") as f:
            f.write("\n".join(lines))

    def generate_battle_briefing(self, data):
        if not data.get('in_battle', False):
            return
            
        lines = ["# [BATTLE: LIVE STATUS]", ""]
        lines.append("## Enemies")
        lines.append("| Name | HP | Position |")
        lines.append("| :--- | :--- | :--- |")
        
        enemies = data.get('enemies', [])
        for e in enemies:
            lines.append(f"| {e['name']} | {e['hp']} | {e.get('pos', 'Front')} |")
            
        lines.append("")
        lines.append("## Party Status")
        for name, stats in data.get('char_stats', {}).items():
            max_mp = stats.get('max_mp', 0)
            if max_mp == 0:
                mp_text = "No MP by design (natural non-caster)"
            else:
                mp_text = f"{stats['mp']}/{max_mp} MP"
            lines.append(f"- **{name}**: {stats['hp']}/{stats['max_hp']} HP, {mp_text}, {stats.get('ip', 0)}% / 100% IP")
            
        lines.append("")
        lines.append("> [!TIP]")
        lines.append("> Use `[PULL: BRIEFING]` during combat if you need a quick inventory check for recovery items.")

        with open(os.path.join(self.data_dir, "battle_briefing.md"), "w") as f:
            f.write("\n".join(lines))

    def generate_shop_briefing(self, town_name, shop_type="Item"):
        """
        Generates a specific shop catalog.
        shop_type can be 'item', 'weapon', 'armor', or 'spell'.
        """
        town_shops = self.shop_data.get(town_name, {})
        if not town_shops:
            # Try fuzzy match if exact town name not found (e.g., 'Alunze Kingdom' vs 'Alunze')
            for t in self.shop_data:
                if town_name.lower() in t.lower() or t.lower() in town_name.lower():
                    town_shops = self.shop_data[t]
                    break
        
        if not town_shops:
            return f"### SHOP: {town_name} ({shop_type})\nNo shop data found for this town."

        # Map requested shop_type to keys in shop_data.json
        # Note: Item shops are often 'General Shops' in the txt but shop_data.json split them.
        # If shop_type is 'item', we might look for 'weapon' or a specific 'items' key if it existed.
        # Based on my check, shop_data.json has weapon, armor, spell.
        
        target_key = shop_type.lower()
        if target_key == "item":
            # Heuristic: Item shops often sell minor weapons in Lufia, but for this AI we want the list.
            # If no 'items' key, we'll suggest looking for the general shop.
            # I'll add logic to check for a 'general' key too if we ever add it.
            items = town_shops.get("items", town_shops.get("weapon", []))
        else:
            items = town_shops.get(target_key, [])

        if not items:
            return f"### SHOP: {town_name} ({shop_type})\nThis town does not appear to have a dedicated {shop_type} shop."

        lines = [f"### {town_name} {shop_type.upper()} SHOP", ""]
        lines.append("| Item Name | Price (Gold) |")
        lines.append("| :--- | :--- |")
        for item, price in items:
            lines.append(f"| {item} | {price} |")
        
        lines.append("")
        lines.append("> [!TIP]")
        lines.append(f"> Consult your available Gold in the Situational Briefing before purchasing.")
        
        path = os.path.join(self.data_dir, f"{shop_type.lower()}_briefing.md")
        with open(path, "w") as f:
            f.write("\n".join(lines))
        return "\n".join(lines)

    def generate_all(self, data):
        self.generate_party_status(data)
        self.generate_location_briefing(data)
        self.generate_mission_readiness(data)
        self.generate_battle_briefing(data)
        
        # Pre-generate common shops for the current town to have them ready
        town_name = data.get('map_name', '')
        if data.get('loc_type') == "Town":
            self.generate_shop_briefing(town_name, "Item")
            self.generate_shop_briefing(town_name, "Weapon")
            self.generate_shop_briefing(town_name, "Spell")
