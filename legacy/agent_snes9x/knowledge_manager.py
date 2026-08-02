import os
import json
import logging
import subprocess


class KnowledgeManager:
    """
    Manages indexing of data files and generation of synthesized knowledge bundles.
    Handles the reactive [PULL] retrieval mechanism.
    """

    def __init__(self, data_dirs=["data", "agent/memory"]):
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dirs = [self._abs_path(d) for d in data_dirs]
        self.index = {}
        self._build_index()

    def _abs_path(self, *parts):
        return os.path.join(self.project_root, *parts)

    def _read_text_if_exists(self, path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return None

    def _load_json_if_exists(self, path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _maybe_refresh_live_data(self):
        script_path = self._abs_path("extract_real_data.py")
        if os.path.exists(script_path):
            try:
                subprocess.run(["python", script_path], cwd=self.project_root, capture_output=True, timeout=20)
            except Exception as exc:
                logging.debug(f"extract_real_data.py refresh skipped: {exc}")

    def _current_map_name(self):
        live_path = self._abs_path("live_data.json")
        live = self._load_json_if_exists(live_path) or {}
        return live.get("map_name", "Unknown")

    def _build_index(self):
        whitelist = [".json", ".md", ".txt"]
        blacklist_patterns = [
            ".sqlite3", ".bin", ".pickle", ".pyc", ".py", "chroma", "index_metadata",
            "link_lists", "ram_map", "locations.json", "dungeon_flags", "shop_addresses",
            "items_spells", "scenario_items", "shop_data", "emulator_addresses", "characters_bw"
        ]

        for d in self.data_dirs:
            if not os.path.exists(d):
                continue
            for root, _, files in os.walk(d):
                for filename in files:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in whitelist or any(p in filename.lower() for p in blacklist_patterns):
                        continue

                    tag = filename.upper().replace(".JSON", "").replace(".TXT", "").replace(".MD", "")
                    prefix = "SYS"
                    if "mockups" in root.lower():
                        continue
                    elif any(k in tag.lower() for k in ["map", "location", "poi", "cave", "dungeon", "city", "navigation"]):
                        prefix = "LOC"
                    elif any(k in tag.lower() for k in ["character", "party", "team", "stats", "readiness"]):
                        prefix = "TEAM"
                    elif any(k in tag.lower() for k in ["guide", "walkthrough", "mechanics", "summary", "monster"]):
                        prefix = "GUIDE"

                    full_tag = f"{prefix}: {tag}"
                    self.index[full_tag] = os.path.join(root, filename)

        self.index["[PULL: BRIEFING]"] = "internal:briefing"
        self.index["[PULL: SHOP]"] = "internal:shop"
        self.index["[PULL: ITEM_SHOP]"] = "internal:item_p"
        self.index["[PULL: WEAPON_SHOP]"] = "internal:weapon_p"
        self.index["[PULL: SPELL_SHOP]"] = "internal:spell_p"
        self.index["[PULL: BATTLE]"] = "internal:battle"
        self.index["[PULL: PUZZLE]"] = "internal:puzzle"
        self.index["[CMD: LEAVE_TOWN]"] = "internal:leave"
        self.index["[MOVE: NORTH/SOUTH/EAST/WEST <N>]"] = "internal:move"
        self.index["[NAV: EXIT]"] = "internal:nav"
        self.index["[INTERACT]"] = "internal:interact"

        logging.info(f"KnowledgeManager: Indexed {len(self.index)} topics.")

    def get_directory_listing(self):
        return [k for k in self.index.keys() if not k.startswith("internal:")]

    def synthesize_bundle(self, tag):
        if tag == "[PULL: BRIEFING]":
            self._maybe_refresh_live_data()
            bundle = "## CONSOLIDATED SITUATIONAL BRIEFING\n\n"
            paths = [
                self._abs_path("data", "mockups", "location_briefing.md"),
                self._abs_path("data", "mockups", "party_status.md"),
                self._abs_path("data", "mockups", "mission_readiness.md"),
            ]
            found = False
            for path in paths:
                text = self._read_text_if_exists(path)
                if text:
                    found = True
                    bundle += text + "\n\n---\n\n"
            return bundle if found else "## CONSOLIDATED SITUATIONAL BRIEFING\nNo live briefing files were available."

        if tag == "[PULL: SHOP]":
            town = self._current_map_name()
            return (
                f"### SHOP INFORMATION: {town}\n"
                "To see shop contents, specify the type: `[PULL: ITEM_SHOP]`, `[PULL: WEAPON_SHOP]`, or `[PULL: SPELL_SHOP]`. "
                "Use `[PULL: BRIEFING]` to see which are nearby."
            )

        if tag in ["[PULL: ITEM_SHOP]", "[PULL: WEAPON_SHOP]", "[PULL: SPELL_SHOP]", "[PULL: ARMOR_SHOP]"]:
            shop_type = tag.replace("[PULL: ", "").replace("_SHOP]", "").lower()
            path = self._abs_path("data", "mockups", f"{shop_type}_briefing.md")
            text = self._read_text_if_exists(path)
            if text:
                return text
            return f"### {tag}\nNo briefing found for this shop type in the current area. Ensure you are in a town with such a shop."

        if tag == "[PULL: BATTLE]":
            path = self._abs_path("data", "mockups", "battle_briefing.md")
            text = self._read_text_if_exists(path)
            if text:
                return text
            return "### BATTLE BRIEFING\nNo active battle data found. This command is only valid during combat."

        if tag == "[PULL: PUZZLE]":
            summary_path = self._abs_path("data", "Tactical Summary.json")
            map_name = self._current_map_name()
            summary = self._load_json_if_exists(summary_path)

            if summary:
                try:
                    dungeons = summary.get("dungeons", summary) if isinstance(summary, dict) else []
                    entries = dungeons if isinstance(dungeons, list) else list(dungeons.values()) if isinstance(dungeons, dict) else []
                    match = None
                    for entry in entries:
                        name = entry.get("name", "") if isinstance(entry, dict) else ""
                        if map_name.lower() in name.lower() or name.lower() in map_name.lower():
                            match = entry
                            break

                    if match:
                        puzzles = match.get("puzzles", match.get("rooms", []))
                        bundle = f"## DUNGEON PUZZLE DATA: {map_name}\n\n"
                        for p in puzzles:
                            pname = p.get("name", "Room")
                            desc = p.get("description", p.get("solution", "No solution data."))
                            bundle += f"### {pname}\n{desc}\n\n"
                        return bundle

                    return (
                        f"## PUZZLE: {map_name}\n"
                        "No specific puzzle data found for this dungeon. General advice: look for levers, pressure plates, "
                        "pushable pillars, and alternate interaction tiles. Use `Reset` (Select) if the room is deadlocked."
                    )
                except Exception as e:
                    return f"## PUZZLE\nFailed to load Tactical Summary: {e}"
            return "## PUZZLE\nNo Tactical Summary data available."

        if tag == "[CMD: LEAVE_TOWN]":
            return (
                "### NAVIGATION: LEAVE TOWN\n"
                "To leave the current town, head towards the town exit coordinates provided in your location briefing or map context."
            )

        filepath = self.index.get(tag)
        if not filepath or filepath.startswith("internal:"):
            return f"ERROR: Knowledge topic '{tag}' not found in directory."

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                if filepath.endswith(".json"):
                    content = json.load(f)
                    return f"### {tag}\n```json\n{json.dumps(content, indent=2)}\n```"
                return f"### {tag}\n{f.read()}"
        except Exception as e:
            return f"ERROR: Failed to read knowledge bundle '{tag}': {e}"

    def resolve_pull_requests(self, response_text):
        import re
        skip_prefixes = ("MOVE:", "NAV:", "INTERACT", "BATTLE:")
        pull_matches = [
            t for t in re.findall(r"\[PULL: (.*?)\]", response_text)
            if not any(t.upper().startswith(p) for p in skip_prefixes)
            and re.search(r"[a-zA-Z0-9]", t)
        ]
        cmd_matches = [
            t for t in re.findall(r"\[CMD: (.*?)\]", response_text)
            if not any(t.upper().startswith(p) for p in skip_prefixes)
            and re.search(r"[a-zA-Z0-9]", t)
        ]

        bundles = []
        for tag in pull_matches + cmd_matches:
            tag = tag.strip()
            full_tag_pull = f"[PULL: {tag}]"
            full_tag_cmd = f"[CMD: {tag}]"

            if full_tag_pull in self.index:
                bundles.append(self.synthesize_bundle(full_tag_pull))
            elif full_tag_cmd in self.index:
                bundles.append(self.synthesize_bundle(full_tag_cmd))
            elif tag in self.index:
                bundles.append(self.synthesize_bundle(tag))
            else:
                matched = False
                for k in self.index.keys():
                    if tag.lower() in k.lower():
                        bundles.append(self.synthesize_bundle(k))
                        matched = True
                        break
                if not matched:
                    bundles.append(f"ERROR: Could not resolve PULL request for '{tag}'.")

        return "\n\n---\n\n".join(bundles) if bundles else None
