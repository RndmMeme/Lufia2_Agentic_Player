"""Update dungeon stubs with correct map_ids from zones.txt."""

import re
from pathlib import Path

ZONES_FILE = Path("data/terrorwave_reference/tables/zones.txt")
AGENT_DUNGEONS_DIR = Path("agent/dungeons")

# Parse zones.txt: "05:05 Secret Skills Cave" or "06:06,07 Sundletan Cave"
zones = {}
for line in ZONES_FILE.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    # Format: "ID:IDs Name" or "ID:ID1,ID2 Name"
    match = re.match(r"^([0-9A-F]{2}):([0-9A-F,]+)\s+(.+)$", line)
    if match:
        zone_id, sub_ids, name = match.groups()
        # Take the first sub_id as the primary map_id
        primary_id = int(sub_ids.split(",")[0], 16)
        zones[name] = primary_id

# Map directory names to zone names
DIR_TO_ZONE = {
    "Alunze_Castle_Basement": "Alunze Castle",
    "Alunze_Northwest_Cave": "Alunze Cave",
    "Ancient_Tower": "Ancient Tower",
    "Cave_To_Bound_Kingdom": "Cave Bridge",
    "Cave_to_Sundletan": "Sundletan Cave",
    "Dankirk_North_Dungeon": "Dankirk Dungeon",
    "Daos' Shrine": "Daos Shrine",
    "Divine_Shrine": "Divine Shrine",
    "Dragon_Mountain": "Dragon Mountain",
    "Flower_Mountain": "Flower Mountain",
    "Gordovan_West_Tower": "Gordovan Tower",
    "Gratze_Castle": "Gratze Castle",
    "Kamirno_Tower": "Kamirno Tower",
    "Karlloon_North_Shrine": "Karlloon Shrine",
    "Lake_Cave": "Lake Cave",
    "Mountain_Of_No_Return": "Mountain of No Return",
    "Northeast_Tower": "Northeast Tower",
    "Northern_Labyrinth": "Northern Labyrinth",
    "Northern_Lighthouse": "Northern Lighthouse",
    "Phantom_Tree_Mountain": "Phantom Tree Mountain",
    "Ruby_Cave": "Ruby Cave",
    "Secret_Skills_Cave": "Secret Skills Cave",
    "Shrine_Of_Vengeance": "Shrine of Vengeance",
    "Shuman_Tower": "Shuman Tower",
    "Strahda_Tower": "Strahda Tower",
    "Tanbel_Southeast_Tower": "Tanbel Tower",
    "Tower_Of_Sacrifice": "Tower of Sacrifice",
    "Tower_Of_Truth": "Tower of Truth",
    "Treasure_Sword_Shrine": "Treasure Sword Shrine",
}

# Update each stub file with the correct map_id
for dir_name, zone_name in DIR_TO_ZONE.items():
    map_id = zones.get(zone_name)
    if map_id is None:
        print(f"WARNING: {zone_name} not found in zones.txt")
        continue

    filename = dir_name.lower().replace("'", "").replace(" ", "_") + ".py"
    filepath = AGENT_DUNGEONS_DIR / filename

    if not filepath.exists():
        print(f"WARNING: {filename} not found")
        continue

    content = filepath.read_text(encoding="utf-8")
    # Replace map_id: int = 0 with actual map_id
    new_content = content.replace("map_id: int = 0  # TODO: assign actual map_id", f"map_id: int = {map_id}")
    filepath.write_text(new_content, encoding="utf-8")
    print(f"UPDATE: {filename} -> map_id={map_id} ({zone_name})")

print(f"\nDone. {len(DIR_TO_ZONE)} dungeon stubs updated.")
