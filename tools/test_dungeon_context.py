import json
import unittest

from agent.dungeon_context import DungeonContextRegistry
from agent.tutorial_guide import TutorialGuide


class DungeonContextRegistryTests(unittest.TestCase):
    def test_room_landmark_alignment_forbids_false_global_projection(self):
        context = DungeonContextRegistry().context(5, 25, 26, radius=3)
        self.assertFalse(context["coordinate_semantics_available"])
        self.assertEqual(context["runtime_alignment"], "room_landmarks")
        self.assertIn("Do not project", context["warning"])

    def test_directional_priors_are_soft_and_use_compiled_cells(self):
        registry = DungeonContextRegistry()
        priors = registry.directional_priors(5, 28, 27, distance=2)
        self.assertEqual(priors, {})

    def test_unregistered_map_has_no_curated_direction_prior(self):
        self.assertEqual(DungeonContextRegistry().directional_priors(0xFE, 1, 1), {})

    def test_navigation_briefing_keeps_visual_map_without_fake_player_marker(self):
        briefing = DungeonContextRegistry().navigation_briefing(5, 28, 20)
        self.assertTrue(briefing["available"])
        self.assertFalse(briefing["coordinate_semantics_available"])
        self.assertIsNone(briefing["ascii_crop"])
        self.assertTrue(briefing["full_map_image"].endswith("navigation_preview.png"))
        self.assertNotIn("suggest", json.dumps(briefing).casefold())
        self.assertIn("LLM", briefing["policy"])

    def test_room_three_teaches_arrow_bridge_without_move_command(self):
        context = TutorialGuide().context(5, 28, 20)
        self.assertTrue(context["active"])
        lessons = " ".join(item["lesson"] for item in context["current_lessons"])
        self.assertIn("Arrow", lessons)
        self.assertIn("bridge", lessons)
        self.assertNotIn("move east", lessons.casefold())


if __name__ == "__main__":
    unittest.main()
