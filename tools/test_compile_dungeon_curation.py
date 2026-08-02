import unittest

from tools.compile_dungeon_curation import (
    anchor_cell,
    intersected_cells,
    primary_cells,
    resolve_cell,
    terrain_conflict,
    validate_marker_fields,
)


class CompileDungeonCurationTests(unittest.TestCase):
    def test_shifted_16px_marker_preserves_pixel_coverage_and_one_anchor(self):
        marker = {
            "x_px": 8,
            "y_px": 8,
            "width_px": 16,
            "height_px": 16,
        }
        self.assertEqual(anchor_cell(marker), (1, 1))
        self.assertEqual(len(intersected_cells(marker)), 4)
        self.assertEqual(
            [cell["coordinate"] for cell in primary_cells(marker)],
            ["B2"],
        )

    def test_32px_marker_compiles_to_four_primary_cells(self):
        marker = {
            "x_px": 16,
            "y_px": 16,
            "width_px": 32,
            "height_px": 32,
        }
        self.assertEqual(
            [cell["coordinate"] for cell in primary_cells(marker)],
            ["B2", "C2", "B3", "C3"],
        )

    def test_walkable_and_lava_are_a_terrain_conflict(self):
        self.assertTrue(terrain_conflict({"walkable", "lava"}))
        self.assertFalse(terrain_conflict({"lava", "puzzle"}))
        self.assertFalse(terrain_conflict({"bush", "switch"}))

    def test_dynamic_object_makes_walkable_cell_conditional(self):
        resolved = resolve_cell(
            [
                {"type": "walkable", "traversal": "confirmed_walkable"},
                {"type": "bush", "traversal": "conditional"},
            ]
        )
        self.assertEqual(resolved["effective_traversal"], "conditional")
        self.assertFalse(resolved["conflict"])

    def test_semantic_mismatch_includes_safe_fix_suggestion(self):
        findings = validate_marker_fields(
            {
                "id": "marker-1",
                "type": "walkable",
                "traversal": "blocked",
                "x_px": 0,
                "y_px": 0,
                "width_px": 16,
                "height_px": 16,
                "snap_px": 1,
            },
            (32, 32),
        )
        mismatch = next(item for item in findings if item["code"] == "walkable_marked_blocked")
        self.assertIn("suggested_fix", mismatch)


if __name__ == "__main__":
    unittest.main()
