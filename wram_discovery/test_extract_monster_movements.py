import unittest

from wram_discovery.extract_monster_movements import (
    MOVEMENT_COUNT,
    MOVEMENT_TABLE_OFFSET,
    extract_movements,
)


class ExtractMonsterMovementsTests(unittest.TestCase):
    def test_joins_sprite_id_to_movement_mode(self):
        rom = bytearray(MOVEMENT_TABLE_OFFSET + MOVEMENT_COUNT)
        rom[MOVEMENT_TABLE_OFFSET + 0x2E] = 0x2F
        monsters = [
            {
                "monster_id": 0x3B,
                "monster_id_hex": "3B",
                "overworld_sprite_id": 0xAE,
                "overworld_sprite_id_hex": "AE",
                "name": "Ramia",
            }
        ]

        payload = extract_movements(bytes(rom), monsters)

        self.assertEqual(payload["monsters"][0]["movement_mode"], 0x2F)
        self.assertEqual(payload["monsters"][0]["movement_mode_hex"], "2F")


if __name__ == "__main__":
    unittest.main()
