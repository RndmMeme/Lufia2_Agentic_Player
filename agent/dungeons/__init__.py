"""Dungeon-specific puzzle and feedback logic."""

from .base import BaseDungeon
from .secret_skills_cave import SecretSkillsCave

DUNGEON_REGISTRY: dict[int, type[BaseDungeon]] = {
    5: SecretSkillsCave,
}

# Map_id -> Dungeon class name mapping from zones.txt and emulator/maps/Dungeons/
DUNGEON_NAMES: dict[int, str] = {
    5: "Secret Skills Cave",
    6: "Sundletan Cave",
    10: "Lake Cave",
    15: "Alunze Castle",
    24: "Alunze Cave",
    30: "Tanbel Tower",
    39: "Ruby Cave",
    48: "Treasure Sword Shrine",
    55: "Gordovan Tower",
    64: "Cave Bridge",
    75: "Ancient Tower",
    96: "Phantom Tree Mountain",
    108: "Tower of Sacrifice",
    117: "Karlloon Shrine",
    126: "Flower Mountain",
    140: "Dankirk Dungeon",
    163: "Mountain of No Return",
    168: "Divine Shrine",
    174: "Shrine of Vengeance",
    183: "Tower of Truth",
    192: "Dragon Mountain",
    209: "Gratze Castle",
    218: "Shuman Tower",
    222: "Strahda Tower",
    226: "Kamirno Tower",
    230: "Daos Shrine",
}

def get_dungeon(map_id: int) -> type[BaseDungeon] | None:
    return DUNGEON_REGISTRY.get(map_id)

def get_dungeon_name(map_id: int) -> str | None:
    return DUNGEON_NAMES.get(map_id)

__all__ = ["BaseDungeon", "get_dungeon", "get_dungeon_name", "DUNGEON_REGISTRY", "DUNGEON_NAMES"]
