import unittest

from agent.navigation.tile_buffer import TileBufferRegistry


class TileBufferRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = TileBufferRegistry()

    def test_secret_cave_live_coordinate_address_formula(self):
        registration = self.registry.registration(5)
        self.assertIsNotNone(registration)
        buffer = registration["buffer"]
        self.assertEqual(self.registry._address(buffer, 28, 55), 0x4C92)
        self.assertEqual(self.registry._address(buffer, 28, 54), 0x4C58)
        self.assertEqual(self.registry._address(buffer, 29, 52), 0x4BE5)

    def test_context_is_small_and_marks_actor_feet(self):
        data = bytearray(0x20000)
        data[0x4C92] = 0x21
        data[0x4C58] = 0x00
        data[0x4C91] = 0x08
        context = self.registry.context(5, 28, 55, bytes(data), radius=1)
        self.assertTrue(context["available"])
        self.assertEqual(context["rows"][1][1], "@")
        west = next(cell for cell in context["cardinal_cells"] if cell["relative"] == [-1, 0])
        self.assertEqual(west["family"], "obstacle")

    def test_diff_excludes_actor_occupancy_but_keeps_environment_change(self):
        before = bytearray(0x20000)
        after = bytearray(before)
        before[0x4C92], after[0x4C92] = 0x21, 0x20
        before[0x4C58], after[0x4C58] = 0x00, 0x01
        bush = self.registry._address(self.registry.registration(5)["buffer"], 30, 52)
        before[bush], after[bush] = 0x08, 0x00
        result = self.registry.diff(
            5, bytes(before), bytes(after), ignore_live_points={(28, 55), (28, 54)}
        )
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["semantic_count"], 1)
        self.assertEqual(result["occupancy_count"], 0)
        self.assertEqual(result["changes"][0]["before_family"], "obstacle")
        self.assertEqual(result["changes"][0]["after_family"], "plain_floor")

    def test_same_family_occupancy_motion_is_not_semantic_progress(self):
        registration = self.registry.registration(5)
        before = bytearray(0x20000)
        after = bytearray(before)
        old = self.registry._address(registration["buffer"], 10, 10)
        new = self.registry._address(registration["buffer"], 10, 11)
        before[old], after[old] = 0x01, 0x00
        before[new], after[new] = 0x00, 0x01
        result = self.registry.diff(5, bytes(before), bytes(after))
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["semantic_count"], 0)
        self.assertEqual(result["occupancy_count"], 2)


if __name__ == "__main__":
    unittest.main()
