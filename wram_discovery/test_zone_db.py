import unittest

from emulator.zone_db import MAP_TO_ZONE, ZONE_DB, zone_for_map


class ZoneDbTests(unittest.TestCase):
    def test_parses_complete_authoritative_table(self):
        self.assertEqual(len(ZONE_DB), 75)
        self.assertEqual(len(MAP_TO_ZONE), 242)

    def test_overworld_and_secret_skills_cave(self):
        self.assertEqual(zone_for_map(0x00)["name"], "Overworld")
        self.assertEqual(zone_for_map(0x05)["name"], "Secret Skills Cave")

    def test_floor_maps_resolve_to_parent_zone(self):
        zone = zone_for_map(0x07)
        self.assertEqual(zone["id"], 0x06)
        self.assertEqual(zone["name"], "Sundletan Cave")
        self.assertEqual(zone["map_ids"], (0x06, 0x07))


if __name__ == "__main__":
    unittest.main()
