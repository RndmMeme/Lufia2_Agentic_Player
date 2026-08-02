import unittest

from tools.dungeon_curation_editor import (
    coordinate_for_pixel,
    covered_coordinates,
    snap_marker_origin,
)


class DungeonCurationEditorModelTests(unittest.TestCase):
    def test_32px_marker_centers_on_click_and_snaps_to_16px_grid(self):
        self.assertEqual(snap_marker_origin(49, 49, 32, 32, 16), (32, 32))
        self.assertEqual(snap_marker_origin(63, 63, 32, 32, 16), (48, 48))

    def test_16px_marker_can_be_positioned_at_pixel_precision(self):
        self.assertEqual(snap_marker_origin(49, 49, 16, 16, 1), (41, 41))
        self.assertEqual(snap_marker_origin(49, 49, 16, 16, 8), (40, 40))

    def test_marker_covers_four_base_grid_cells(self):
        marker = {
            "x_px": 32,
            "y_px": 48,
            "width_px": 32,
            "height_px": 32,
        }
        self.assertEqual(
            covered_coordinates(marker),
            ["C4", "D4", "C5", "D5"],
        )

    def test_shifted_16px_marker_reports_every_overlapped_navigation_cell(self):
        marker = {
            "x_px": 41,
            "y_px": 41,
            "width_px": 16,
            "height_px": 16,
        }
        self.assertEqual(
            covered_coordinates(marker),
            ["C3", "D3", "C4", "D4"],
        )

    def test_pixel_coordinate_uses_16px_reference_grid(self):
        self.assertEqual(coordinate_for_pixel(0, 0), "A1")
        self.assertEqual(coordinate_for_pixel(28 * 16, 54 * 16), "AC55")


if __name__ == "__main__":
    unittest.main()
