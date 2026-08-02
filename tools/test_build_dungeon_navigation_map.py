import unittest

from tools.build_dungeon_navigation_map import (
    chess_coordinate,
    column_label,
    visual_state,
)


class DungeonNavigationMapTests(unittest.TestCase):
    def test_column_labels(self):
        self.assertEqual(column_label(0), "A")
        self.assertEqual(column_label(25), "Z")
        self.assertEqual(column_label(26), "AA")
        self.assertEqual(column_label(28), "AC")
        self.assertEqual(column_label(74), "BW")

    def test_runtime_coordinate_label(self):
        self.assertEqual(chess_coordinate(28, 54), "AC55")

    def test_black_center_is_hard_wall(self):
        state, confidence = visual_state(
            {
                "content_ratio": 0.50,
                "center_content_ratio": 0.10,
                "floor_ratio": 0.80,
            }
        )
        self.assertEqual(state, "black_wall")
        self.assertEqual(confidence, 1.0)

    def test_floor_prior_is_conservative(self):
        wall_like, _ = visual_state(
            {
                "content_ratio": 1.0,
                "center_content_ratio": 1.0,
                "floor_ratio": 0.40,
            }
        )
        floor_like, _ = visual_state(
            {
                "content_ratio": 1.0,
                "center_content_ratio": 1.0,
                "floor_ratio": 0.90,
            }
        )
        self.assertEqual(wall_like, "unknown")
        self.assertEqual(floor_like, "likely_walkable")


if __name__ == "__main__":
    unittest.main()
